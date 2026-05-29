"""Integration tests for `HospcallCallingService` schedule dispatch + the
sequential multi-hospital fan-out (one schedule -> ordered targets dialed
one at a time).

Run: `env=test make test tests/integration/test_dispatch_schedule.py`
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from calling.models import CallAttempt, CallSchedule, CallScheduleHospital
from calling.vars import (
    CallScheduleStatus,
    CallStatus,
    ScheduleTargetStatus,
)
from hospital.models import Hospital
from hospital.vars import HospitalOwnership, HospitalSource
from prompt.models import Prompt
from services.external.blandai import BlandAIResponseStatus
from services.internal.hospcall_calling.service import (
    _PRONUNCIATION_GUIDE,
    HospcallCallingService,
)

pytestmark = pytest.mark.django_db


def _independent(name='Test Vet', **overrides):
    # INDEPENDENT + a phone — an eligible target for `dispatch_schedule`.
    defaults = dict(
        name=name,
        source=HospitalSource.MANUAL.value,
        ownership=HospitalOwnership.INDEPENDENT.value,
        phone_e164='+15551234567',
    )
    defaults.update(overrides)
    return Hospital.objects.create(**defaults)


@pytest.fixture
def hospital():
    return _independent()


@pytest.fixture
def prompt():
    return Prompt.objects.create(
        name='dispatch-schedule-test', version=1, body='test body'
    )


def _make_schedule(hospitals, prompt, **overrides):
    """Create a schedule with an ordered target per hospital."""
    defaults = dict(
        prompt=prompt,
        scheduled_at=timezone.now(),
        status=CallScheduleStatus.PENDING,
    )
    defaults.update(overrides)
    schedule = CallSchedule.objects.create(**defaults)
    CallScheduleHospital.objects.bulk_create(
        [
            CallScheduleHospital(schedule=schedule, hospital=h, order=i)
            for i, h in enumerate(hospitals)
        ]
    )
    return schedule


def _complete(service, attempt):
    """Mark an attempt COMPLETED and run the schedule-advance hook, the way
    `refresh_call_attempt` does on a terminal webhook/poll."""
    attempt.status = CallStatus.COMPLETED
    attempt.save(update_fields=['status'])
    service._on_attempt_finished(attempt)


# ── single target (legacy 1:1 behaviour, now via a 1-target schedule) ────────


def test_dispatch_creates_attempt_and_marks_dispatched(hospital, prompt, mocker):
    schedule = _make_schedule([hospital], prompt)
    spy = mocker.patch('calling.tasks.send_call.apply_async')

    out = HospcallCallingService().dispatch_schedule(
        schedule_id=schedule.id,
        expected_scheduled_at_iso=schedule.scheduled_at.isoformat(),
    )

    assert out['result'] == 'dispatched'
    schedule.refresh_from_db()
    assert schedule.status == CallScheduleStatus.DISPATCHED
    attempt = CallAttempt.objects.get(schedule=schedule)
    assert attempt.status == CallStatus.QUEUED
    target = schedule.targets.get()
    assert target.status == ScheduleTargetStatus.DIALING
    assert target.call_attempt_id == attempt.id
    spy.assert_called_once_with(kwargs={'call_attempt_id': attempt.id})


def test_dispatch_superseded_when_scheduled_at_changed(hospital, prompt):
    schedule = _make_schedule([hospital], prompt)
    out = HospcallCallingService().dispatch_schedule(
        schedule_id=schedule.id,
        expected_scheduled_at_iso='2020-01-01T00:00:00+00:00',
    )
    assert out['result'] == 'superseded'
    schedule.refresh_from_db()
    assert schedule.status == CallScheduleStatus.PENDING
    assert not CallAttempt.objects.filter(schedule=schedule).exists()


def test_dispatch_not_pending_when_already_dispatched(hospital, prompt):
    schedule = _make_schedule(
        [hospital], prompt, status=CallScheduleStatus.DISPATCHED
    )
    out = HospcallCallingService().dispatch_schedule(
        schedule_id=schedule.id,
        expected_scheduled_at_iso=schedule.scheduled_at.isoformat(),
    )
    assert out['result'] == 'not_pending'


def test_dispatch_not_found_when_deleted():
    out = HospcallCallingService().dispatch_schedule(
        schedule_id=999_999,
        expected_scheduled_at_iso='2026-01-01T00:00:00+00:00',
    )
    assert out['result'] == 'not_found'


def test_dispatch_skips_non_independent_hospital(prompt, mocker):
    mocker.patch('calling.tasks.send_call.apply_async')
    h = Hospital.objects.create(
        name='VCA Chain Vet',
        source=HospitalSource.MANUAL.value,
        ownership=HospitalOwnership.CHAIN.value,
    )
    schedule = _make_schedule([h], prompt)
    out = HospcallCallingService().dispatch_schedule(
        schedule_id=schedule.id,
        expected_scheduled_at_iso=schedule.scheduled_at.isoformat(),
    )
    assert out['result'] == 'skipped'
    schedule.refresh_from_db()
    assert schedule.status == CallScheduleStatus.SKIPPED
    assert not CallAttempt.objects.filter(schedule=schedule).exists()
    assert schedule.targets.get().status == ScheduleTargetStatus.SKIPPED


def test_dispatch_skips_hospital_with_excluded_reason(hospital, prompt, mocker):
    mocker.patch('calling.tasks.send_call.apply_async')
    hospital.excluded_reason = 'not_operational'
    hospital.save(update_fields=['excluded_reason'])
    schedule = _make_schedule([hospital], prompt)
    out = HospcallCallingService().dispatch_schedule(
        schedule_id=schedule.id,
        expected_scheduled_at_iso=schedule.scheduled_at.isoformat(),
    )
    assert out['result'] == 'skipped'
    schedule.refresh_from_db()
    assert schedule.status == CallScheduleStatus.SKIPPED


# ── sequential multi-hospital fan-out ───────────────────────────────────────


def test_dispatch_dials_only_the_first_target(prompt, mocker):
    spy = mocker.patch('calling.tasks.send_call.apply_async')
    h0, h1, h2 = _independent('A'), _independent('B'), _independent('C')
    schedule = _make_schedule([h0, h1, h2], prompt)

    HospcallCallingService().dispatch_schedule(
        schedule_id=schedule.id,
        expected_scheduled_at_iso=schedule.scheduled_at.isoformat(),
    )

    # Exactly one call placed; the rest wait their turn.
    assert CallAttempt.objects.filter(schedule=schedule).count() == 1
    spy.assert_called_once()
    statuses = list(
        schedule.targets.order_by('order').values_list('status', flat=True)
    )
    assert statuses == [
        ScheduleTargetStatus.DIALING,
        ScheduleTargetStatus.PENDING,
        ScheduleTargetStatus.PENDING,
    ]


def test_completion_chains_to_next_then_completes(prompt, mocker):
    mocker.patch('calling.tasks.send_call.apply_async')
    service = HospcallCallingService()
    h0, h1 = _independent('A'), _independent('B')
    schedule = _make_schedule([h0, h1], prompt)
    service.dispatch_schedule(
        schedule_id=schedule.id,
        expected_scheduled_at_iso=schedule.scheduled_at.isoformat(),
    )

    first = CallAttempt.objects.get(schedule=schedule, hospital=h0)
    _complete(service, first)

    # Second hospital now dialing; first done.
    second = CallAttempt.objects.get(schedule=schedule, hospital=h1)
    assert second.status == CallStatus.QUEUED
    t0, t1 = schedule.targets.order_by('order')
    assert t0.status == ScheduleTargetStatus.DONE
    assert t1.status == ScheduleTargetStatus.DIALING

    _complete(service, second)
    schedule.refresh_from_db()
    assert schedule.status == CallScheduleStatus.COMPLETED
    assert CallAttempt.objects.filter(schedule=schedule).count() == 2


def test_completion_advance_is_idempotent(prompt, mocker):
    mocker.patch('calling.tasks.send_call.apply_async')
    service = HospcallCallingService()
    h0, h1 = _independent('A'), _independent('B')
    schedule = _make_schedule([h0, h1], prompt)
    service.dispatch_schedule(
        schedule_id=schedule.id,
        expected_scheduled_at_iso=schedule.scheduled_at.isoformat(),
    )

    first = CallAttempt.objects.get(schedule=schedule, hospital=h0)
    first.status = CallStatus.COMPLETED
    first.save(update_fields=['status'])
    # Webhook AND reconcile both finish the same call.
    service._on_attempt_finished(first)
    service._on_attempt_finished(first)

    # The second hospital is dialed exactly once despite the double finish.
    assert CallAttempt.objects.filter(schedule=schedule, hospital=h1).count() == 1


def test_uncallable_target_in_sequence_is_skipped(prompt, mocker):
    mocker.patch('calling.tasks.send_call.apply_async')
    service = HospcallCallingService()
    h0 = _independent('A')
    chain = Hospital.objects.create(
        name='Chain', source=HospitalSource.MANUAL.value,
        ownership=HospitalOwnership.CHAIN.value,
    )
    h2 = _independent('C')
    schedule = _make_schedule([h0, chain, h2], prompt)
    service.dispatch_schedule(
        schedule_id=schedule.id,
        expected_scheduled_at_iso=schedule.scheduled_at.isoformat(),
    )

    first = CallAttempt.objects.get(schedule=schedule, hospital=h0)
    _complete(service, first)

    # The chain target is skipped without a call; h2 is dialed next.
    t0, t1, t2 = schedule.targets.order_by('order')
    assert t0.status == ScheduleTargetStatus.DONE
    assert t1.status == ScheduleTargetStatus.SKIPPED
    assert t2.status == ScheduleTargetStatus.DIALING
    assert not CallAttempt.objects.filter(schedule=schedule, hospital=chain).exists()
    assert CallAttempt.objects.filter(schedule=schedule, hospital=h2).exists()


# ── send_call idempotency + reconcile rescue (no real double-dial / no stall) ─


def _fake_response(mocker, *, call_id, status=BlandAIResponseStatus.SUCCESS):
    return mocker.Mock(call_id=call_id, status=status, message=None)


def test_send_call_is_idempotent_under_redelivery(hospital, prompt, mocker):
    # acks_late redelivery must NOT place a second real call.
    mocker.patch('services.internal.hospcall_calling.service.get_client')
    service = HospcallCallingService()
    service.blandai.send_call.return_value = _fake_response(mocker, call_id='b-1')
    attempt = CallAttempt.objects.create(
        hospital=hospital, prompt=prompt, status=CallStatus.QUEUED
    )

    service.send_call(call_attempt_id=attempt.id)
    service.send_call(call_attempt_id=attempt.id)  # redelivery

    assert service.blandai.send_call.call_count == 1
    attempt.refresh_from_db()
    assert attempt.status == CallStatus.IN_PROGRESS
    assert attempt.blandai_call_id == 'b-1'


def test_send_call_passes_pronunciation_guide(hospital, prompt, mocker):
    # The Dr.Tail pronunciation guide must reach BlandAI on every call —
    # a refactor that drops it should fail here, not pass silently.
    mocker.patch('services.internal.hospcall_calling.service.get_client')
    service = HospcallCallingService()
    service.blandai.send_call.return_value = _fake_response(mocker, call_id='b-1')
    attempt = CallAttempt.objects.create(
        hospital=hospital, prompt=prompt, status=CallStatus.QUEUED
    )

    service.send_call(call_attempt_id=attempt.id)

    config = service.blandai.send_call.call_args[0][0]
    assert config.pronunciation_guide == list(_PRONUNCIATION_GUIDE)


def test_send_call_success_without_call_id_fails(hospital, prompt, mocker):
    mocker.patch('services.internal.hospcall_calling.service.get_client')
    service = HospcallCallingService()
    service.blandai.send_call.return_value = _fake_response(mocker, call_id=None)
    attempt = CallAttempt.objects.create(
        hospital=hospital, prompt=prompt, status=CallStatus.QUEUED
    )

    service.send_call(call_attempt_id=attempt.id)

    attempt.refresh_from_db()
    assert attempt.status == CallStatus.FAILED


def test_reconcile_rescues_stale_queued_schedule_attempt(hospital, prompt, mocker):
    spy = mocker.patch('calling.tasks.send_call.apply_async')
    schedule = _make_schedule([hospital], prompt)
    attempt = CallAttempt.objects.create(
        schedule=schedule, hospital=hospital, prompt=prompt,
        status=CallStatus.QUEUED,
    )
    # created_at is auto_now_add — bump it into the past via UPDATE.
    CallAttempt.objects.filter(id=attempt.id).update(
        created_at=timezone.now() - timedelta(minutes=10)
    )

    out = HospcallCallingService().reconcile_in_progress_calls()

    assert out['rescued'] == 1
    spy.assert_called_once_with(kwargs={'call_attempt_id': attempt.id})


def test_reconcile_skips_fresh_queued_attempt(hospital, prompt, mocker):
    spy = mocker.patch('calling.tasks.send_call.apply_async')
    schedule = _make_schedule([hospital], prompt)
    CallAttempt.objects.create(
        schedule=schedule, hospital=hospital, prompt=prompt,
        status=CallStatus.QUEUED,
    )

    out = HospcallCallingService().reconcile_in_progress_calls()

    assert out['rescued'] == 0
    spy.assert_not_called()
