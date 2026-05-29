"""Integration tests for `SourcingService` — covers the idempotency guard
that the harness's AC mandates (DRT-5204 AC #3, DRT-5265).

Real DB required (`@pytest.mark.django_db`). Celery enqueue is mocked at
the boundary so we don't actually fan out tasks; we just verify the row
state and the guard logic.
"""

from __future__ import annotations

import pytest

from services.internal.sourcing.service import (
    SourcingAlreadyRunning,
    SourcingJobNotFound,
    SourcingService,
)
from sourcing.models import SourcingJob
from sourcing.vars import SourcingJobStatus


@pytest.mark.django_db
def test_trigger_job_creates_pending_row_and_enqueues(no_celery_dispatch) -> None:
    job = SourcingService().trigger_job(
        triggered_by_id=None,
        state_code='CA', city='Los Angeles',
        max_depth=6, call_limit=300,
    )
    assert job.status == SourcingJobStatus.PENDING
    assert job.state_code == 'CA'
    assert job.city == 'Los Angeles'
    assert job.max_depth == 6
    assert job.call_limit == 300
    assert no_celery_dispatch.called
    assert no_celery_dispatch.call_args.kwargs['kwargs']['job_id'] == job.pk


@pytest.mark.django_db
def test_trigger_job_stores_overridden_guardrails(no_celery_dispatch) -> None:
    job = SourcingService().trigger_job(
        triggered_by_id=None,
        state_code='NY', city='New York',
        max_depth=8, call_limit=500,
    )
    assert job.max_depth == 8
    assert job.call_limit == 500


@pytest.mark.django_db
def test_duplicate_trigger_for_same_region_raises(no_celery_dispatch) -> None:
    svc = SourcingService()
    svc.trigger_job(
        triggered_by_id=None,
        state_code='CA', city='Los Angeles',
        max_depth=6, call_limit=300,
    )
    with pytest.raises(SourcingAlreadyRunning) as exc_info:
        svc.trigger_job(
            triggered_by_id=None,
            state_code='CA', city='Los Angeles',
            max_depth=6, call_limit=300,
        )
    assert exc_info.value.state_code == 'CA'
    assert exc_info.value.city == 'Los Angeles'


@pytest.mark.django_db
def test_duplicate_trigger_allowed_for_different_city(no_celery_dispatch) -> None:
    svc = SourcingService()
    svc.trigger_job(
        triggered_by_id=None, state_code='CA', city='Los Angeles',
        max_depth=6, call_limit=300,
    )
    # Same state, different city — must NOT raise.
    job2 = svc.trigger_job(
        triggered_by_id=None, state_code='CA', city='San Diego',
        max_depth=6, call_limit=300,
    )
    assert job2.city == 'San Diego'


@pytest.mark.django_db
def test_duplicate_guard_does_not_count_completed_jobs(no_celery_dispatch) -> None:
    """A previously COMPLETED job shouldn't block a fresh trigger."""
    svc = SourcingService()
    first = svc.trigger_job(
        triggered_by_id=None, state_code='NY', city='Brooklyn',
        max_depth=6, call_limit=300,
    )
    SourcingJob.objects.filter(pk=first.pk).update(status=SourcingJobStatus.COMPLETED)

    # Should not raise — first job is no longer active.
    second = svc.trigger_job(
        triggered_by_id=None, state_code='NY', city='Brooklyn',
        max_depth=6, call_limit=300,
    )
    assert second.status == SourcingJobStatus.PENDING


@pytest.mark.django_db
def test_cancel_job_flips_status(no_celery_dispatch) -> None:
    svc = SourcingService()
    job = svc.trigger_job(
        triggered_by_id=None, state_code='WA', city='Seattle',
        max_depth=6, call_limit=300,
    )
    cancelled = svc.cancel_job(job.pk)
    assert cancelled.status == SourcingJobStatus.CANCELLED
    assert cancelled.completed_at is not None


@pytest.mark.django_db
def test_cancel_job_idempotent_on_already_completed(no_celery_dispatch) -> None:
    svc = SourcingService()
    job = svc.trigger_job(
        triggered_by_id=None, state_code='WA', city='Seattle',
        max_depth=6, call_limit=300,
    )
    SourcingJob.objects.filter(pk=job.pk).update(status=SourcingJobStatus.COMPLETED)
    result = svc.cancel_job(job.pk)
    # Cancel against a terminal job is a no-op — status stays COMPLETED.
    assert result.status == SourcingJobStatus.COMPLETED


@pytest.mark.django_db
def test_cancel_job_missing_raises() -> None:
    with pytest.raises(SourcingJobNotFound):
        SourcingService().cancel_job(999_999)
