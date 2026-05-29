"""Integration tests for the backoffice hospital endpoints — focused on the
`call_attempt_count` annotation and the calls `?hospital=` filter."""

from __future__ import annotations

import uuid

import pytest
from django.test import Client

from calling.models import CallAttempt, CallSchedule
from calling.vars import CallStatus
from hospital.models import Hospital
from hospital.vars import HospitalOwnership, HospitalSource

pytestmark = pytest.mark.django_db

BACKOFFICE_TOKEN = 'test-backoffice-token'


@pytest.fixture(autouse=True)
def _backoffice_token(settings):
    settings.BACKOFFICE_API_TOKEN = BACKOFFICE_TOKEN


@pytest.fixture
def client() -> Client:
    return Client()


def _make_hospital(**overrides) -> Hospital:
    """Create a non-deleted Hospital. A unique `source_external_id` keeps the
    `uq_hospital_source_external` constraint happy across calls."""

    fields = {
        'name': 'Test Vet',
        'source': HospitalSource.MANUAL.value,
        'source_external_id': f'hosp-test-{uuid.uuid4().hex[:12]}',
        'is_deleted': False,
    }
    fields.update(overrides)
    return Hospital.objects.create(**fields)


def _make_attempts(hospital: Hospital, count: int) -> None:
    for _ in range(count):
        CallAttempt.objects.create(hospital=hospital, status=CallStatus.QUEUED)


# ---- GET /hospitals/ — call_attempt_count ----------------------------------

def test_list_includes_call_attempt_count(client: Client) -> None:
    hospital = _make_hospital(name='Counted Vet')
    _make_attempts(hospital, 3)

    response = client.get('/backoffice/hospitals/')
    assert response.status_code == 200
    rows = {row['id']: row for row in response.json()['results']}
    assert rows[hospital.id]['call_attempt_count'] == 3


def test_list_call_attempt_count_excludes_soft_deleted(client: Client) -> None:
    # A soft-deleted CallAttempt must not inflate the count badge — the badge
    # has to agree with the call-history list, which filters is_deleted=False.
    hospital = _make_hospital(name='Partly Deleted Vet')
    _make_attempts(hospital, 2)
    CallAttempt.objects.create(
        hospital=hospital, status=CallStatus.QUEUED, is_deleted=True
    )

    response = client.get('/backoffice/hospitals/')
    rows = {row['id']: row for row in response.json()['results']}
    assert rows[hospital.id]['call_attempt_count'] == 2


def test_detail_call_attempt_count_excludes_soft_deleted(client: Client) -> None:
    hospital = _make_hospital()
    _make_attempts(hospital, 3)
    CallAttempt.objects.create(
        hospital=hospital, status=CallStatus.QUEUED, is_deleted=True
    )

    response = client.get(f'/backoffice/hospitals/{hospital.id}/')
    assert response.status_code == 200
    assert response.json()['call_attempt_count'] == 3


def test_list_call_attempt_count_zero_without_attempts(client: Client) -> None:
    hospital = _make_hospital(name='Uncalled Vet')

    response = client.get('/backoffice/hospitals/')
    rows = {row['id']: row for row in response.json()['results']}
    assert rows[hospital.id]['call_attempt_count'] == 0


def test_list_call_attempt_count_counts_all_statuses(client: Client) -> None:
    # The operator wants total contact volume — every attempt counts,
    # regardless of status.
    hospital = _make_hospital()
    CallAttempt.objects.create(hospital=hospital, status=CallStatus.QUEUED)
    CallAttempt.objects.create(hospital=hospital, status=CallStatus.COMPLETED)
    CallAttempt.objects.create(hospital=hospital, status=CallStatus.FAILED)

    response = client.get('/backoffice/hospitals/')
    rows = {row['id']: row for row in response.json()['results']}
    assert rows[hospital.id]['call_attempt_count'] == 3


def test_list_call_attempt_count_isolated_per_hospital(client: Client) -> None:
    called = _make_hospital(name='Called Vet')
    other = _make_hospital(name='Other Vet')
    _make_attempts(called, 2)
    _make_attempts(other, 5)

    response = client.get('/backoffice/hospitals/')
    rows = {row['id']: row for row in response.json()['results']}
    assert rows[called.id]['call_attempt_count'] == 2
    assert rows[other.id]['call_attempt_count'] == 5


# ---- GET /hospitals/<id>/ — call_attempt_count -----------------------------

def test_detail_includes_call_attempt_count(client: Client) -> None:
    hospital = _make_hospital()
    _make_attempts(hospital, 4)

    response = client.get(f'/backoffice/hospitals/{hospital.id}/')
    assert response.status_code == 200
    assert response.json()['call_attempt_count'] == 4


def test_detail_call_attempt_count_zero_without_attempts(client: Client) -> None:
    hospital = _make_hospital()

    response = client.get(f'/backoffice/hospitals/{hospital.id}/')
    assert response.json()['call_attempt_count'] == 0


# ---- HospitalLv1Serializer robustness on a non-annotated instance ----------

def test_serializer_call_attempt_count_robust_without_annotation(
    client: Client,
) -> None:
    # A plain (non-annotated) Hospital instance — e.g. one fetched outside
    # the list/detail querysets — must serialize `call_attempt_count` as 0
    # rather than raise an AttributeError.
    from api.backoffice.hospitals.serializers import HospitalLv1Serializer

    hospital = _make_hospital(name='Plain Vet')
    serialized = HospitalLv1Serializer(hospital).data
    assert serialized['call_attempt_count'] == 0


# ---- GET /calls/?hospital=<id> ---------------------------------------------

def test_calls_filter_by_hospital_returns_only_that_hospital(client: Client) -> None:
    target = _make_hospital(name='Target Vet')
    other = _make_hospital(name='Other Vet')
    _make_attempts(target, 2)
    _make_attempts(other, 3)

    response = client.get(f'/backoffice/calls/?hospital={target.id}')
    assert response.status_code == 200
    rows = response.json()['results']
    assert len(rows) == 2
    assert {row['hospital_id'] for row in rows} == {target.id}


def test_calls_without_hospital_filter_returns_all(client: Client) -> None:
    target = _make_hospital(name='Target Vet')
    other = _make_hospital(name='Other Vet')
    _make_attempts(target, 2)
    _make_attempts(other, 3)

    response = client.get('/backoffice/calls/')
    assert response.status_code == 200
    hospital_ids = {row['hospital_id'] for row in response.json()['results']}
    assert target.id in hospital_ids
    assert other.id in hospital_ids


def test_calls_filter_by_non_numeric_hospital_returns_400(client: Client) -> None:
    # A non-numeric `?hospital=` would reach the DB and raise — validate it up
    # front so the operator gets a clean 400 instead of a 500.
    response = client.get('/backoffice/calls/?hospital=abc')
    assert response.status_code == 400


def test_calls_filter_by_non_numeric_schedule_returns_400(client: Client) -> None:
    response = client.get('/backoffice/calls/?schedule=abc')
    assert response.status_code == 400


# ---- GET /hospitals/?ownership= --------------------------------------------

def test_hospitals_filter_by_ownership_returns_only_matching(
    client: Client,
) -> None:
    independent = _make_hospital(
        name='Independent Vet', ownership=HospitalOwnership.INDEPENDENT.value
    )
    chain = _make_hospital(
        name='Chain Vet', ownership=HospitalOwnership.CHAIN.value
    )

    response = client.get(
        f'/backoffice/hospitals/?ownership={HospitalOwnership.INDEPENDENT.value}'
    )
    assert response.status_code == 200
    rows = response.json()['results']
    ids = {row['id'] for row in rows}
    assert independent.id in ids
    assert chain.id not in ids
    # Every returned row matches the requested ownership.
    assert all(
        row['ownership'] == HospitalOwnership.INDEPENDENT.value for row in rows
    )


def test_hospitals_filter_ownership_and_q_compose(client: Client) -> None:
    # `?ownership=` and `?q=` AND-compose: only a hospital matching BOTH the
    # ownership axis and the name typeahead comes back.
    wanted = _make_hospital(
        name='Maple Independent Vet',
        ownership=HospitalOwnership.INDEPENDENT.value,
    )
    # Right name, wrong ownership.
    _make_hospital(
        name='Maple Chain Vet', ownership=HospitalOwnership.CHAIN.value
    )
    # Right ownership, wrong name.
    _make_hospital(
        name='Birch Independent Vet',
        ownership=HospitalOwnership.INDEPENDENT.value,
    )

    response = client.get(
        f'/backoffice/hospitals/?ownership={HospitalOwnership.INDEPENDENT.value}&q=Maple'
    )
    assert response.status_code == 200
    ids = {row['id'] for row in response.json()['results']}
    assert ids == {wanted.id}


def test_hospitals_without_ownership_filter_returns_all(client: Client) -> None:
    independent = _make_hospital(
        name='Independent Vet', ownership=HospitalOwnership.INDEPENDENT.value
    )
    chain = _make_hospital(
        name='Chain Vet', ownership=HospitalOwnership.CHAIN.value
    )

    response = client.get('/backoffice/hospitals/')
    assert response.status_code == 200
    ids = {row['id'] for row in response.json()['results']}
    assert independent.id in ids
    assert chain.id in ids


def test_hospitals_filter_by_invalid_ownership_returns_400(
    client: Client,
) -> None:
    # An out-of-set `?ownership=` would silently return zero rows — reject it
    # so the operator sees a clean 400 instead of an empty list.
    response = client.get('/backoffice/hospitals/?ownership=NOT_A_REAL_VALUE')
    assert response.status_code == 400
    assert 'ownership' in response.json()


def test_calls_filter_hospital_and_schedule_and_compose(client: Client) -> None:
    # `?hospital=` and `?schedule=` together must AND-compose: only attempts
    # matching BOTH come back.
    target = _make_hospital(name='Target Vet')
    other = _make_hospital(name='Other Vet')
    schedule = CallSchedule.objects.create(
        scheduled_at='2026-05-12T10:00:00Z'
    )

    # Matches both filters.
    wanted = CallAttempt.objects.create(
        hospital=target, schedule=schedule, status=CallStatus.QUEUED
    )
    # Right hospital, wrong schedule.
    CallAttempt.objects.create(hospital=target, status=CallStatus.QUEUED)
    # Right schedule, wrong hospital.
    CallAttempt.objects.create(
        hospital=other, schedule=schedule, status=CallStatus.QUEUED
    )

    response = client.get(
        f'/backoffice/calls/?hospital={target.id}&schedule={schedule.id}'
    )
    assert response.status_code == 200
    rows = response.json()['results']
    assert [row['id'] for row in rows] == [wanted.id]
