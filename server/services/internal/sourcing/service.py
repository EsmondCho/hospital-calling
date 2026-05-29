"""Hospital sourcing orchestration (DRT-5204 §2, DRT-5265).

Public entry point for the backoffice. Two responsibilities:
  - `trigger_job`: validate input, guard against duplicate trigger,
    create `SourcingJob` row, enqueue `start_job`.
  - `cancel_job`: flip status to CANCELLED; the running tile fan-out
    checks status on each step and exits cleanly.

The Celery task pipeline itself lives in `tasks.py`.
"""

from __future__ import annotations

import structlog
from django.db import transaction
from django.utils import timezone

from sourcing.models import SourcingJob
from sourcing.vars import ACTIVE_STATUSES, TERMINAL_STATUSES, SourcingJobStatus

logger = structlog.get_logger(__name__)


class SourcingAlreadyRunning(Exception):
    def __init__(self, state_code: str, city: str | None):
        self.state_code = state_code
        self.city = city
        super().__init__(
            f'Sourcing job already running for {state_code}/{city or "*"}'
        )


class SourcingJobNotFound(Exception):
    pass


class SourcingService:
    """Stateless orchestrator. Safe to instantiate per request."""

    def trigger_job(
        self,
        *,
        triggered_by_id: int | None,
        state_code: str,
        city: str | None,
        max_depth: int,
        call_limit: int,
    ) -> SourcingJob:
        """Create a SourcingJob row and enqueue the first task in the pipeline.

        The operator supplies only `state_code` + `city` text; the server
        resolves the root viewport and recursively tiles it (DRT-5265).
        `max_depth` / `call_limit` are guardrail overrides (the serializer
        fills them with settings defaults when omitted).

        Rejects with `SourcingAlreadyRunning` (HTTP 409 candidate) when an
        active job already covers the same `(state_code, city)` target.

        The duplicate-check + insert run inside one `transaction.atomic()`
        with `select_for_update` so two simultaneous trigger requests
        can't both pass the check and create competing jobs.
        """

        with transaction.atomic():
            # Plain `select_for_update()` — we WANT to block on the
            # concurrent trigger's lock, see the active row it's
            # operating on, and raise. `skip_locked=True` would skip
            # the locked row and let us create a duplicate.
            existing = (
                SourcingJob.objects
                .select_for_update()
                .filter(state_code=state_code, city=city, status__in=ACTIVE_STATUSES)
                .first()
            )
            if existing is not None:
                raise SourcingAlreadyRunning(state_code=state_code, city=city)

            job = SourcingJob.objects.create(
                triggered_by_id=triggered_by_id,
                state_code=state_code,
                city=city,
                max_depth=max_depth,
                call_limit=call_limit,
            )

        logger.info(
            'sourcing.trigger_job',
            job_id=job.pk,
            state_code=state_code, city=city,
            max_depth=max_depth, call_limit=call_limit,
        )

        # Lazy import: importing `tasks` at module top would pull the task
        # module (and its app imports) into the service's import graph.
        from services.internal.sourcing.tasks import start_job

        start_job.apply_async(kwargs={'job_id': job.pk})
        return job

    def cancel_job(self, job_id: int) -> SourcingJob:
        """Flip the job to CANCELLED so the next task step bails."""

        with transaction.atomic():
            try:
                job = SourcingJob.objects.select_for_update().get(pk=job_id)
            except SourcingJob.DoesNotExist as e:
                raise SourcingJobNotFound(job_id) from e
            if job.status in TERMINAL_STATUSES:
                return job
            job.status = SourcingJobStatus.CANCELLED
            job.completed_at = timezone.now()
            job.save(update_fields=['status', 'completed_at'])
        logger.info('sourcing.cancel_job', job_id=job_id)
        return job
