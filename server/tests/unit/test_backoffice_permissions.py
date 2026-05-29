"""Unit tests for `IsBackofficeToken` permission + mutating endpoints.

Run: `env=test make test tests/unit/test_backoffice_permissions.py`
"""

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from calling.models import CallSchedule, CallScheduleHospital
from calling.vars import CallScheduleStatus
from hospital.models import Hospital
from hospital.vars import HospitalSource
from prompt.models import Prompt

TOKEN = 'test-token-deadbeef'

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def hospital(db):
    return Hospital.objects.create(
        name='Test Vet', source=HospitalSource.MANUAL.value, phone_e164='+15551234567'
    )


@override_settings(BACKOFFICE_API_TOKEN=TOKEN)
def test_post_schedule_rejected_without_token(api_client, hospital):
    response = api_client.post(
        '/backoffice/schedules/',
        {'hospitals': [hospital.id], 'scheduled_at': '2026-05-12T10:00:00Z'},
        format='json',
    )
    assert response.status_code == 403


@override_settings(BACKOFFICE_API_TOKEN=TOKEN)
def test_post_schedule_rejected_with_wrong_token(api_client, hospital):
    response = api_client.post(
        '/backoffice/schedules/',
        {'hospitals': [hospital.id], 'scheduled_at': '2026-05-12T10:00:00Z'},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN='nope',
    )
    assert response.status_code == 403


@override_settings(BACKOFFICE_API_TOKEN='')
def test_post_schedule_fails_closed_when_token_unset(api_client, hospital):
    """Empty server-side token must reject every call (no accidental open prod)."""
    response = api_client.post(
        '/backoffice/schedules/',
        {'hospitals': [hospital.id], 'scheduled_at': '2026-05-12T10:00:00Z'},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 403


@override_settings(BACKOFFICE_API_TOKEN=TOKEN)
def test_post_schedule_accepts_correct_token(api_client, hospital):
    future = (timezone.now() + timedelta(days=1)).isoformat()
    response = api_client.post(
        '/backoffice/schedules/',
        {
            'hospitals': [hospital.id],
            'scheduled_at': future,
            'memo': 'first batch',
        },
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 201, response.content
    schedule = CallSchedule.objects.get(memo='first batch')
    assert list(schedule.targets.values_list('hospital_id', flat=True)) == [
        hospital.id
    ]


@override_settings(BACKOFFICE_API_TOKEN=TOKEN)
def test_get_schedules_still_open(api_client):
    """Read endpoints don't require the backoffice token."""
    response = api_client.get('/backoffice/schedules/')
    assert response.status_code == 200


@override_settings(BACKOFFICE_API_TOKEN=TOKEN)
def test_post_hospital_creates_with_manual_source(api_client, db):
    response = api_client.post(
        '/backoffice/hospitals/',
        {'name': 'Sunset Vet', 'phone_e164': '+15559998888'},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 201, response.content
    hospital = Hospital.objects.get(name='Sunset Vet')
    assert hospital.source == HospitalSource.MANUAL.value
    # Operator-created hospitals auto-lock so a later sourcing run won't
    # re-classify them.
    assert hospital.label_locked is True


# ── Hospital list typeahead ────────────────────────────────────────────────


def test_hospital_list_filters_by_q(api_client, db):
    Hospital.objects.create(name='Pawsy Care Center', source=HospitalSource.MANUAL.value)
    Hospital.objects.create(name='Pawsy Animal Clinic', source=HospitalSource.MANUAL.value)

    response = api_client.get('/backoffice/hospitals/?q=pawsy')
    assert response.status_code == 200
    names = {row['name'] for row in response.json()['results']}
    assert names == {'Pawsy Care Center', 'Pawsy Animal Clinic'}


# ── Hospital UPDATE / DELETE ────────────────────────────────────────────────


@override_settings(BACKOFFICE_API_TOKEN=TOKEN)
def test_patch_hospital_requires_token(api_client, hospital):
    response = api_client.patch(
        f'/backoffice/hospitals/{hospital.id}/',
        {'name': 'New Name'},
        format='json',
    )
    assert response.status_code == 403


@override_settings(BACKOFFICE_API_TOKEN=TOKEN)
def test_patch_hospital_with_token(api_client, hospital):
    response = api_client.patch(
        f'/backoffice/hospitals/{hospital.id}/',
        {'name': 'Renamed Vet', 'timezone': 'America/Los_Angeles'},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 200, response.content
    hospital.refresh_from_db()
    assert hospital.name == 'Renamed Vet'
    assert hospital.timezone == 'America/Los_Angeles'
    # A hand-edit auto-locks the row.
    assert hospital.label_locked is True


@override_settings(BACKOFFICE_API_TOKEN=TOKEN)
def test_patch_hospital_explicit_label_locked_is_honored(api_client, hospital):
    """Passing `label_locked` explicitly overrides the auto-lock — this is
    how an operator deliberately unlocks a row for re-classification."""
    hospital.label_locked = True
    hospital.save(update_fields=['label_locked'])

    response = api_client.patch(
        f'/backoffice/hospitals/{hospital.id}/',
        {'label_locked': False},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 200, response.content
    hospital.refresh_from_db()
    assert hospital.label_locked is False


@override_settings(BACKOFFICE_API_TOKEN=TOKEN)
def test_delete_hospital_with_token_soft_deletes(api_client, hospital):
    hid = hospital.id
    response = api_client.delete(
        f'/backoffice/hospitals/{hid}/',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 204
    # Soft delete: row stays in DB but is_deleted=True so list/detail hide it.
    assert Hospital.objects.filter(id=hid, is_deleted=True).exists()
    assert api_client.get(f'/backoffice/hospitals/{hid}/').status_code == 404


@override_settings(BACKOFFICE_API_TOKEN=TOKEN)
def test_bulk_delete_hospitals(api_client, db):
    h1 = Hospital.objects.create(name='Bulk A', source=HospitalSource.MANUAL.value)
    h2 = Hospital.objects.create(name='Bulk B', source=HospitalSource.MANUAL.value)
    response = api_client.post(
        '/backoffice/hospitals/bulk_delete/',
        {'ids': [h1.id, h2.id]},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 200, response.content
    assert response.json() == {'deleted_count': 2}
    h1.refresh_from_db()
    h2.refresh_from_db()
    assert h1.is_deleted and h2.is_deleted


@override_settings(BACKOFFICE_API_TOKEN=TOKEN)
def test_bulk_delete_rejects_non_int_ids(api_client, db):
    response = api_client.post(
        '/backoffice/hospitals/bulk_delete/',
        {'ids': ['not-an-int']},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 400


# ── Schedule UPDATE / DELETE with PENDING guard ─────────────────────────────


def _make_schedule(hospital, *, status=CallScheduleStatus.PENDING):
    schedule = CallSchedule.objects.create(
        scheduled_at='2026-05-12T10:00:00Z',
        status=status,
    )
    CallScheduleHospital.objects.create(
        schedule=schedule, hospital=hospital, order=0
    )
    return schedule


@override_settings(BACKOFFICE_API_TOKEN=TOKEN)
def test_patch_pending_schedule_succeeds(api_client, hospital):
    schedule = _make_schedule(hospital)
    response = api_client.patch(
        f'/backoffice/schedules/{schedule.id}/',
        {'memo': 'updated memo'},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 200, response.content
    schedule.refresh_from_db()
    assert schedule.memo == 'updated memo'


@override_settings(BACKOFFICE_API_TOKEN=TOKEN)
def test_patch_dispatched_schedule_returns_409(api_client, hospital):
    schedule = _make_schedule(hospital, status=CallScheduleStatus.DISPATCHED)
    response = api_client.patch(
        f'/backoffice/schedules/{schedule.id}/',
        {'memo': 'too late'},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 409


@override_settings(BACKOFFICE_API_TOKEN=TOKEN)
def test_delete_schedule_soft_deletes_regardless_of_status(api_client, hospital):
    pending = _make_schedule(hospital)
    dispatched = _make_schedule(hospital, status=CallScheduleStatus.DISPATCHED)
    for s in (pending, dispatched):
        response = api_client.delete(
            f'/backoffice/schedules/{s.id}/',
            HTTP_X_BACKOFFICE_TOKEN=TOKEN,
        )
        assert response.status_code == 204
        s.refresh_from_db()
        assert s.is_deleted is True


# ── Prompt CRUD with version auto-bump ──────────────────────────────────────


@override_settings(BACKOFFICE_API_TOKEN=TOKEN)
def test_post_prompt_auto_versions(api_client, db):
    Prompt.objects.create(
        name='greeting',
        version=1,
        body='v1 body',
    )
    response = api_client.post(
        '/backoffice/prompts/',
        {
            'name': 'greeting',
            'body': 'v2 body',
        },
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 201, response.content
    payload = response.json()
    assert payload['version'] == 2
    assert Prompt.objects.filter(name='greeting').count() == 2


@override_settings(BACKOFFICE_API_TOKEN=TOKEN)
def test_patch_prompt_edits_version_in_place(api_client, db):
    prompt = Prompt.objects.create(
        name='greeting',
        version=1,
        body='v1',
    )
    response = api_client.patch(
        f'/backoffice/prompts/{prompt.id}/',
        {'body': 'v1 edited'},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 200, response.content
    prompt.refresh_from_db()
    assert prompt.body == 'v1 edited'


@override_settings(BACKOFFICE_API_TOKEN=TOKEN)
def test_delete_prompt_soft_deletes(api_client, db):
    p = Prompt.objects.create(
        name='retire-me',
        version=1,
        body='gone soon',
    )
    response = api_client.delete(
        f'/backoffice/prompts/{p.id}/',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 204
    p.refresh_from_db()
    assert p.is_deleted is True
