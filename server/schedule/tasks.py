"""Beat-driven dispatcher for tasks parked in `ScheduledTask`.

Picks up rows whose `eta` falls inside the next batching window and re-applies
them via celery's normal `apply_async` path. The 10-minute window matches
`HospcallTask.SCHEDULING_BATCH_SECONDS` so a task scheduled 10–20 minutes out is
guaranteed at least one beat tick to enqueue it before the moment arrives.
"""

from datetime import timedelta

import structlog
from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = structlog.get_logger(__name__)


@shared_task(name='schedule.execute_scheduled_tasks')
def execute_scheduled_tasks(*, batch_size: int = 200):
    """Cap batch_size so a beat-downtime backlog can't drain in one tick —
    overflow is left for the next 10-min run, keeping each tick bounded.

    The claim phase (lock + mark dispatched_at) runs inside a single
    `transaction.atomic()` with `select_for_update(skip_locked=True)` so
    overlapping ticks (e.g. worker concurrency=2 picking up the same beat
    fire) can't claim the same row twice. Dispatch happens after commit; if
    `apply_async` fails for a row, we revert its `dispatched_at` to None so
    the next tick can retry.
    """
    from hospcall.celery import HospcallTask, celery_app, unsign_datetime
    from schedule.models import ScheduledTask

    now = timezone.now()

    with transaction.atomic():
        claimed = list(
            ScheduledTask.objects.select_for_update(skip_locked=True)
            .filter(
                eta__lt=now + timedelta(seconds=HospcallTask.SCHEDULING_BATCH_SECONDS),
                dispatched_at__isnull=True,
            )
            .order_by('eta')[:batch_size]
        )
        claimed_ids = [st.id for st in claimed]
        if claimed_ids:
            ScheduledTask.objects.filter(id__in=claimed_ids).update(
                dispatched_at=now
            )

    dispatched = 0
    for st in claimed:
        try:
            func = celery_app.tasks[st.task_name]
            restored_args = (
                tuple(unsign_datetime(a) for a in st.args) if st.args else ()
            )
            restored_kwargs = (
                {k: unsign_datetime(v) for k, v in st.kwargs.items()}
                if st.kwargs
                else {}
            )
            func.apply_async(
                args=restored_args,
                kwargs=restored_kwargs,
                eta=st.eta,
                **st.options,
            )
            dispatched += 1
        except Exception:
            logger.exception(
                'scheduled_task_dispatch_failed',
                scheduled_task_id=st.id,
                task_name=st.task_name,
            )
            # Surrender the claim so the next tick can retry the row.
            ScheduledTask.objects.filter(id=st.id).update(dispatched_at=None)

    return {'dispatched': dispatched}
