"""Celery tasks for HOSPCALL outbound calling.

This file contains *thin* task entry points. Real work lives in
`services.internal.hospcall_calling.service`.

Names registered with Celery: `calling.dispatch_schedule`,
`calling.send_call`, `calling.process_blandai_webhook`,
`calling.reconcile_in_progress_calls`.
"""

from __future__ import annotations

import structlog
from celery import shared_task

logger = structlog.get_logger(__name__)


@shared_task(name='calling.dispatch_schedule')
def dispatch_schedule(*, schedule_id: int, expected_scheduled_at_iso: str) -> dict:
    """Fire a single CallSchedule. Late-binds prompt/hospital state.

    `expected_scheduled_at_iso` is the value snapshotted when the task was
    enqueued; the service compares it to the row's current `scheduled_at`
    and aborts when they differ (the user edited the schedule, a fresher
    task was enqueued, this stale one is the loser).
    """
    from services.internal.hospcall_calling.service import HospcallCallingService

    return HospcallCallingService().dispatch_schedule(
        schedule_id=schedule_id,
        expected_scheduled_at_iso=expected_scheduled_at_iso,
    )


@shared_task(name='calling.send_call', acks_late=True)
def send_call(*, call_attempt_id: int) -> None:
    from services.internal.hospcall_calling.service import HospcallCallingService

    HospcallCallingService().send_call(call_attempt_id=call_attempt_id)


@shared_task(name='calling.process_blandai_webhook', acks_late=True)
def process_blandai_webhook(*, call_attempt_id: int) -> None:
    from services.internal.hospcall_calling.service import HospcallCallingService

    HospcallCallingService().refresh_call_attempt(call_attempt_id=call_attempt_id)


@shared_task(name='calling.reconcile_in_progress_calls')
def reconcile_in_progress_calls() -> dict:
    from services.internal.hospcall_calling.service import HospcallCallingService

    return HospcallCallingService().reconcile_in_progress_calls()
