"""Integration tests for the backoffice call-schedule endpoints — the
past-`scheduled_at` guard, voice/model validation, and the multi-hospital
target fan-out on create.

Run: `env=test make test tests/integration/test_backoffice_schedules.py`
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from calling.models import CallSchedule, CallScheduleHospital
from calling.vars import CallScheduleStatus
from hospital.models import Hospital
from hospital.vars import HospitalSource

TOKEN = 'test-token-deadbeef'

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture(autouse=True)
def _backoffice_token(settings):
    settings.BACKOFFICE_API_TOKEN = TOKEN


@pytest.fixture(autouse=True)
def _no_enqueue(mocker):
    # The view enqueues `dispatch_schedule` on save — block the real Celery
    # call so these tests stay at the HTTP edge.
    return mocker.patch(
        'api.backoffice.schedules.views.dispatch_schedule_task.apply_async'
    )


def _hospital(name='Test Vet') -> Hospital:
    return Hospital.objects.create(
        name=name, source=HospitalSource.MANUAL.value, phone_e164='+15551234567'
    )


@pytest.fixture
def hospital() -> Hospital:
    return _hospital()


def _future() -> str:
    return (timezone.now() + timedelta(days=1)).isoformat()


# ── scheduled_at guard ───────────────────────────────────────────────────────


def test_create_with_past_scheduled_at_returns_400(api_client, hospital):
    past = timezone.now() - timedelta(hours=1)
    response = api_client.post(
        '/backoffice/schedules/',
        {'hospitals': [hospital.id], 'scheduled_at': past.isoformat()},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 400
    assert 'scheduled_at' in response.json()


def test_create_with_future_scheduled_at_succeeds(api_client, hospital):
    response = api_client.post(
        '/backoffice/schedules/',
        {'hospitals': [hospital.id], 'scheduled_at': _future()},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 201, response.content


def test_patch_with_past_scheduled_at_returns_400(api_client):
    schedule = CallSchedule.objects.create(
        scheduled_at=timezone.now() + timedelta(days=1),
        status=CallScheduleStatus.PENDING,
    )
    past = timezone.now() - timedelta(hours=1)
    response = api_client.patch(
        f'/backoffice/schedules/{schedule.id}/',
        {'scheduled_at': past.isoformat()},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 400
    assert 'scheduled_at' in response.json()


def test_patch_omitting_scheduled_at_succeeds(api_client):
    # A PATCH that touches only `memo` must not trip the scheduled_at or
    # hospitals validators (field validators only run for present fields).
    schedule = CallSchedule.objects.create(
        scheduled_at=timezone.now() + timedelta(days=1),
        status=CallScheduleStatus.PENDING,
    )
    response = api_client.patch(
        f'/backoffice/schedules/{schedule.id}/',
        {'memo': 'updated memo'},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 200, response.content
    assert response.json()['memo'] == 'updated memo'


# ── multi-hospital targets ───────────────────────────────────────────────────


def test_create_fans_out_to_ordered_targets(api_client):
    h0, h1, h2 = _hospital('A'), _hospital('B'), _hospital('C')
    response = api_client.post(
        '/backoffice/schedules/',
        {'hospitals': [h0.id, h1.id, h2.id], 'scheduled_at': _future()},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 201, response.content
    schedule_id = response.json()['id']
    targets = list(
        CallScheduleHospital.objects.filter(schedule_id=schedule_id).order_by(
            'order'
        )
    )
    assert [t.hospital_id for t in targets] == [h0.id, h1.id, h2.id]
    assert [t.order for t in targets] == [0, 1, 2]


def test_create_dedupes_hospitals_preserving_order(api_client):
    h0, h1 = _hospital('A'), _hospital('B')
    response = api_client.post(
        '/backoffice/schedules/',
        {'hospitals': [h0.id, h1.id, h0.id], 'scheduled_at': _future()},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 201, response.content
    schedule_id = response.json()['id']
    assert [
        t.hospital_id
        for t in CallScheduleHospital.objects.filter(
            schedule_id=schedule_id
        ).order_by('order')
    ] == [h0.id, h1.id]


def test_create_without_hospitals_returns_400(api_client):
    response = api_client.post(
        '/backoffice/schedules/',
        {'scheduled_at': _future()},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 400
    assert 'hospitals' in response.json()


def test_create_with_unknown_hospital_returns_400(api_client, hospital):
    response = api_client.post(
        '/backoffice/schedules/',
        {'hospitals': [hospital.id, 999_999], 'scheduled_at': _future()},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 400
    assert 'hospitals' in response.json()


def test_list_row_carries_targets_and_count(api_client):
    h0, h1 = _hospital('A'), _hospital('B')
    api_client.post(
        '/backoffice/schedules/',
        {'hospitals': [h0.id, h1.id], 'scheduled_at': _future()},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    response = api_client.get('/backoffice/schedules/')
    assert response.status_code == 200, response.content
    row = response.json()['results'][0]
    assert row['hospital_count'] == 2
    assert [t['hospital_id'] for t in row['targets']] == [h0.id, h1.id]


# ── voice / model on create ─────────────────────────────────────────────────


def test_create_with_explicit_voice_and_model_persists(api_client, hospital):
    response = api_client.post(
        '/backoffice/schedules/',
        {
            'hospitals': [hospital.id],
            'scheduled_at': _future(),
            'voice': 'ryan',
            'model': 'turbo',
        },
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body['voice'] == 'ryan'
    assert body['model'] == 'turbo'


def test_create_without_voice_and_model_uses_defaults(api_client, hospital):
    response = api_client.post(
        '/backoffice/schedules/',
        {'hospitals': [hospital.id], 'scheduled_at': _future()},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body['voice'] == 'random'
    assert body['model'] == 'base'


def test_create_with_invalid_voice_returns_400(api_client, hospital):
    response = api_client.post(
        '/backoffice/schedules/',
        {
            'hospitals': [hospital.id],
            'scheduled_at': _future(),
            'voice': 'not-a-real-voice',
        },
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 400
    assert 'voice' in response.json()


def test_create_with_invalid_model_returns_400(api_client, hospital):
    response = api_client.post(
        '/backoffice/schedules/',
        {
            'hospitals': [hospital.id],
            'scheduled_at': _future(),
            'model': 'enhanced',  # legacy value, no longer valid
        },
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 400
    assert 'model' in response.json()
