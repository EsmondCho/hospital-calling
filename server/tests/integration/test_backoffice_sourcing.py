"""End-to-end coverage for the backoffice sourcing REST endpoints
(DRT-5204 §2)."""

from __future__ import annotations

import json
import uuid

import pytest
from django.test import Client

from hospital.models import Hospital
from hospital.vars import HospitalSource
from sourcing.models import City, SourcingJob
from sourcing.vars import SourcingJobStatus


BACKOFFICE_TOKEN = 'test-backoffice-token'


@pytest.fixture(autouse=True)
def _backoffice_token(settings):
    settings.BACKOFFICE_API_TOKEN = BACKOFFICE_TOKEN


@pytest.fixture
def client() -> Client:
    return Client()


def _post_trigger(client: Client, **overrides) -> tuple[int, dict]:
    payload = {
        'state_code': 'CA',
        'city': 'Los Angeles',
    }
    payload.update(overrides)
    response = client.post(
        '/backoffice/sourcing/jobs/',
        data=json.dumps(payload),
        content_type='application/json',
        HTTP_X_BACKOFFICE_TOKEN=BACKOFFICE_TOKEN,
    )
    return response.status_code, response.json() if response.content else {}


# ---- POST /jobs/ -----------------------------------------------------------

@pytest.mark.django_db
def test_trigger_creates_pending_job(client, no_celery_dispatch):
    code, body = _post_trigger(client)
    assert code == 201
    assert body['status'] == SourcingJobStatus.PENDING
    assert body['state_code'] == 'CA'
    assert body['city'] == 'Los Angeles'
    assert SourcingJob.objects.count() == 1
    assert no_celery_dispatch.called


@pytest.mark.django_db
def test_trigger_rejects_missing_token(client, no_celery_dispatch):
    response = client.post(
        '/backoffice/sourcing/jobs/',
        data=json.dumps({'state_code': 'CA', 'city': 'Los Angeles'}),
        content_type='application/json',
        # No X-Backoffice-Token header.
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_trigger_rejects_invalid_state(client, no_celery_dispatch):
    code, body = _post_trigger(client, state_code='california')
    assert code == 400
    assert 'state_code' in body


@pytest.mark.django_db
def test_trigger_accepts_optional_guardrail_overrides(client, no_celery_dispatch):
    code, body = _post_trigger(client, max_depth=8, call_limit=500)
    assert code == 201
    assert body['max_depth'] == 8
    assert body['call_limit'] == 500


@pytest.mark.django_db
def test_trigger_defaults_guardrails_when_omitted(client, no_celery_dispatch, settings):
    code, body = _post_trigger(client)
    assert code == 201
    assert body['max_depth'] == settings.SOURCING_MAX_DEPTH
    assert body['call_limit'] == settings.SOURCING_CALL_LIMIT


@pytest.mark.django_db
def test_trigger_rejects_out_of_range_max_depth(client, no_celery_dispatch):
    code, _ = _post_trigger(client, max_depth=99)
    assert code == 400


@pytest.mark.django_db
def test_trigger_rejects_out_of_range_call_limit(client, no_celery_dispatch):
    code, _ = _post_trigger(client, call_limit=99999)
    assert code == 400


@pytest.mark.django_db
def test_duplicate_trigger_returns_409(client, no_celery_dispatch):
    code1, _ = _post_trigger(client)
    code2, body2 = _post_trigger(client)
    assert code1 == 201
    assert code2 == 409
    assert 'Sourcing job already running' in body2.get('detail', '')


# ---- GET /jobs/{id}/ -------------------------------------------------------

@pytest.mark.django_db
def test_detail_returns_lv2_fields(client, no_celery_dispatch):
    code, body = _post_trigger(client)
    response = client.get(f'/backoffice/sourcing/jobs/{body["id"]}/')
    assert response.status_code == 200
    data = response.json()
    # Lv2-only fields must be present.
    for k in ['started_at', 'completed_at', 'llm_input_tokens',
              'call_count', 'max_depth', 'call_limit',
              'root_south', 'root_west', 'root_north', 'root_east']:
        assert k in data
    # Dropped legacy fields must be gone.
    for k in ['latitude', 'longitude', 'page_cursor', 'last_place_id', 'radius_km']:
        assert k not in data


# ---- POST /jobs/{id}/cancel/ -----------------------------------------------

@pytest.mark.django_db
def test_cancel_flips_status(client, no_celery_dispatch):
    code, body = _post_trigger(client)
    response = client.post(
        f'/backoffice/sourcing/jobs/{body["id"]}/cancel/',
        HTTP_X_BACKOFFICE_TOKEN=BACKOFFICE_TOKEN,
    )
    assert response.status_code == 200
    assert response.json()['status'] == SourcingJobStatus.CANCELLED


@pytest.mark.django_db
def test_cancel_missing_returns_404(client, no_celery_dispatch):
    response = client.post(
        '/backoffice/sourcing/jobs/999999/cancel/',
        HTTP_X_BACKOFFICE_TOKEN=BACKOFFICE_TOKEN,
    )
    assert response.status_code == 404


def _make_hospital(**overrides) -> Hospital:
    """Create a non-deleted Hospital for endpoint-counting tests. A unique
    `source_external_id` keeps the `uq_hospital_source_external` constraint
    happy across calls."""

    fields = {
        'name': 'Test Vet',
        'source': HospitalSource.MANUAL,
        'source_external_id': f'city-test-{uuid.uuid4().hex[:12]}',
        'is_deleted': False,
    }
    fields.update(overrides)
    return Hospital.objects.create(**fields)


# ---- GET /states/ ----------------------------------------------------------

@pytest.mark.django_db
def test_states_lists_states_with_hospital_counts(client):
    # `WY` is absent from the dummy seed, so its count is fully ours.
    _make_hospital(state='WY', city='Cheyenne')
    _make_hospital(state='WY', city='Casper')

    response = client.get('/backoffice/sourcing/states/')
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    by_state = {row['state_code']: row['hospital_count'] for row in body}
    assert by_state['WY'] == 2


@pytest.mark.django_db
def test_states_omits_states_with_zero_hospitals(client):
    _make_hospital(state='WY', city='Cheyenne')
    hospital = _make_hospital(state='ND', city='Fargo')
    hospital.is_deleted = True
    hospital.save(update_fields=['is_deleted'])

    response = client.get('/backoffice/sourcing/states/')
    state_codes = {row['state_code'] for row in response.json()}
    assert 'WY' in state_codes
    # ND's only hospital is soft-deleted → the state drops out.
    assert 'ND' not in state_codes


@pytest.mark.django_db
def test_states_excludes_deleted_hospitals_from_count(client):
    _make_hospital(state='WY', city='Cheyenne')
    deleted = _make_hospital(state='WY', city='Casper')
    deleted.is_deleted = True
    deleted.save(update_fields=['is_deleted'])

    response = client.get('/backoffice/sourcing/states/')
    by_state = {row['state_code']: row['hospital_count'] for row in response.json()}
    assert by_state['WY'] == 1


@pytest.mark.django_db
def test_states_folds_state_code_casing(client):
    # `Hospital.state` is free-form — a lowercase manual entry and an
    # uppercase one are the same state and must collapse into one row.
    _make_hospital(state='wy', city='Cheyenne')
    _make_hospital(state='WY', city='Casper')

    response = client.get('/backoffice/sourcing/states/')
    wy_rows = [r for r in response.json() if r['state_code'] == 'WY']
    assert len(wy_rows) == 1
    assert wy_rows[0]['hospital_count'] == 2


@pytest.mark.django_db
def test_states_is_open_without_token(client):
    response = client.get('/backoffice/sourcing/states/')
    assert response.status_code == 200


# ---- GET /cities/ ----------------------------------------------------------

@pytest.mark.django_db
def test_cities_requires_state_param(client):
    response = client.get('/backoffice/sourcing/cities/')
    assert response.status_code == 400
    assert 'detail' in response.json()


@pytest.mark.django_db
def test_cities_rejects_malformed_state(client):
    for bad in ['california', 'C', 'ca', '12']:
        response = client.get(f'/backoffice/sourcing/cities/?state={bad}')
        assert response.status_code == 400, bad


@pytest.mark.django_db
def test_cities_unknown_state_returns_empty_list(client):
    # `PR` satisfies the ^[A-Z]{2}$ guard but has no preloaded `City`
    # rows — the endpoint returns 200 with [], not a 400 or 500.
    response = client.get('/backoffice/sourcing/cities/?state=PR')
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.django_db
def test_cities_returns_full_abc_sorted_list_from_city_table(client):
    # The 0005 data migration preloaded `city`; CA carries thousands of rows.
    response = client.get('/backoffice/sourcing/cities/?state=CA')
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    names = [row['name'] for row in body]
    assert 'Los Angeles' in names
    assert names == sorted(names, key=str.lower)


@pytest.mark.django_db
def test_cities_counts_hospitals_case_insensitively(client):
    # `WY` carries no dummy-seed hospitals, so the count is exactly ours.
    _make_hospital(state='WY', city='Cheyenne')
    _make_hospital(state='WY', city='cheyenne')   # lowercase — same city
    deleted = _make_hospital(state='WY', city='Cheyenne')
    deleted.is_deleted = True
    deleted.save(update_fields=['is_deleted'])

    response = client.get('/backoffice/sourcing/cities/?state=WY')
    by_name = {row['name']: row for row in response.json()}
    # Two non-deleted rows, raw-string casing collapsed; deleted one excluded.
    assert by_name['Cheyenne']['hospital_count'] == 2


@pytest.mark.django_db
def test_cities_counts_hospitals_with_lowercase_state(client):
    # `WY` carries no dummy-seed hospitals. A hospital stored with a
    # lowercase state code still counts toward the uppercase query param.
    _make_hospital(state='wy', city='Cheyenne')
    _make_hospital(state='WY', city='Cheyenne')

    response = client.get('/backoffice/sourcing/cities/?state=WY')
    by_name = {row['name']: row for row in response.json()}
    assert by_name['Cheyenne']['hospital_count'] == 2


@pytest.mark.django_db
def test_cities_sourced_flag_reflects_sourcing_jobs(client):
    # Only a COMPLETED job marks a city sourced.
    SourcingJob.objects.create(
        state_code='CA', city='los angeles',
        status=SourcingJobStatus.COMPLETED,
    )
    # A failed job does not count — the city still needs sourcing.
    SourcingJob.objects.create(
        state_code='CA', city='san francisco',
        status=SourcingJobStatus.FAILED,
    )

    response = client.get('/backoffice/sourcing/cities/?state=CA')
    by_name = {row['name']: row for row in response.json()}
    # Job's `city` lowercases to match the `City` row name.
    assert by_name['Los Angeles']['sourced'] is True
    assert by_name['San Francisco']['sourced'] is False
    # A city with no job stays unsourced.
    assert by_name['San Diego']['sourced'] is False


@pytest.mark.django_db
def test_cities_zero_count_and_unsourced_by_default(client):
    extra = City.objects.create(state_code='CA', name='Acalanes Ridge Extra')

    response = client.get('/backoffice/sourcing/cities/?state=CA')
    by_name = {row['name']: row for row in response.json()}
    assert by_name[extra.name]['hospital_count'] == 0
    assert by_name[extra.name]['sourced'] is False


@pytest.mark.django_db
def test_cities_hospital_count_ignores_other_states(client):
    # `WY` carries no dummy-seed hospitals. A hospital in another state
    # with the same city name must not leak into WY's count.
    _make_hospital(state='WY', city='Cheyenne')
    _make_hospital(state='CO', city='Cheyenne')

    response = client.get('/backoffice/sourcing/cities/?state=WY')
    by_name = {row['name']: row for row in response.json()}
    assert by_name['Cheyenne']['hospital_count'] == 1


@pytest.mark.django_db
def test_cities_matches_census_city_suffix(client):
    """A `City` row with a Census ` City` suffix ('Boise City') must count
    hospitals — and reflect jobs — whose Google-derived city drops it
    ('Boise'). Otherwise the dropdown shows a freshly-sourced city as
    `hospital_count: 0`."""
    City.objects.get_or_create(state_code='ID', name='Boise City')
    _make_hospital(state='ID', city='Boise')
    _make_hospital(state='ID', city='Boise')
    SourcingJob.objects.create(
        state_code='ID', city='Boise', status=SourcingJobStatus.COMPLETED,
    )

    response = client.get('/backoffice/sourcing/cities/?state=ID')
    by_name = {row['name']: row for row in response.json()}
    assert by_name['Boise City']['hospital_count'] == 2
    assert by_name['Boise City']['sourced'] is True


@pytest.mark.django_db
def test_cities_matches_census_town_suffix(client):
    """The ` Town` suffix (New England Census names) is normalized the same
    way as ` City` — 'Agawam Town' must match a hospital city of 'Agawam'."""
    City.objects.get_or_create(state_code='MA', name='Agawam Town')
    _make_hospital(state='MA', city='Agawam')

    response = client.get('/backoffice/sourcing/cities/?state=MA')
    by_name = {row['name']: row for row in response.json()}
    assert by_name['Agawam Town']['hospital_count'] == 1


@pytest.mark.django_db
def test_cities_is_open_without_token(client):
    response = client.get('/backoffice/sourcing/cities/?state=CA')
    assert response.status_code == 200


# ---- GET /jobs/ ------------------------------------------------------------

@pytest.mark.django_db
def test_list_returns_paginated_lv1_rows(client, no_celery_dispatch):
    _post_trigger(client, state_code='CA', city='Los Angeles')
    _post_trigger(client, state_code='NY', city='Brooklyn')

    response = client.get('/backoffice/sourcing/jobs/')
    assert response.status_code == 200
    body = response.json()
    assert 'results' in body
    assert {row['state_code'] for row in body['results']} == {'CA', 'NY'}
    # Lv1 surface — partial / tile-progress fields surface in the list so
    # operators can spot a partial job without opening the detail view.
    sample = body['results'][0]
    for k in ['status', 'fetched_count', 'inserted_count', 'actual_cost_usd',
              'partial', 'partial_reason', 'total_tiles', 'completed_tiles',
              'capped_tile_count', 'failed_tile_count']:
        assert k in sample
    # Lv2-only fields stay off the list surface.
    for k in ['call_count', 'llm_input_tokens', 'root_south']:
        assert k not in sample


# ---- GET /jobs/<id>/events/ (SSE) -----------------------------------------

@pytest.mark.django_db
def test_events_returns_404_for_missing_job(client):
    response = client.get('/backoffice/sourcing/jobs/999999/events/')
    assert response.status_code == 404
    # The error body must survive `ServerSentEventRenderer.render()` — DRF
    # routes the 404 through it, and a non-bytes return would corrupt it.
    # Parse `.content` directly: the SSE-only renderer stamps the response
    # `text/event-stream`, so the test client's `.json()` helper refuses it.
    assert json.loads(response.content)['detail'] == 'SourcingJob 999999 not found'


@pytest.mark.django_db
def test_events_stream_emits_done_for_terminal_job(client, no_celery_dispatch):
    _, body = _post_trigger(client)
    SourcingJob.objects.filter(pk=body['id']).update(
        status=SourcingJobStatus.COMPLETED,
    )

    # Drive the generator directly — Django's StreamingHttpResponse leaves
    # it open until the consumer pulls. Pulling the first few frames is
    # enough to verify the terminal `event: done` path emits before the
    # 30-minute cap kicks in.
    from api.backoffice.sourcing.views import _job_event_stream
    frames = []
    for frame in _job_event_stream(body['id']):
        frames.append(frame)
        if b'event: done' in frame:
            break

    assert any(b'event: done' in f for f in frames)
    # The first data frame should carry the Lv2 status=COMPLETED snapshot.
    assert any(b'"status": "COMPLETED"' in f for f in frames)


@pytest.mark.django_db
def test_events_accepts_event_stream_accept_header(client, no_celery_dispatch):
    """Regression: browser `EventSource` always sends
    `Accept: text/event-stream`. With only `JSONRenderer` configured
    globally, DRF content negotiation rejected it with 406 before the
    view ran. `ServerSentEventRenderer` on the view fixes that."""
    _, body = _post_trigger(client)
    SourcingJob.objects.filter(pk=body['id']).update(
        status=SourcingJobStatus.COMPLETED,
    )

    response = client.get(
        f'/backoffice/sourcing/jobs/{body["id"]}/events/',
        HTTP_ACCEPT='text/event-stream',
    )

    assert response.status_code == 200
    assert response['Content-Type'] == 'text/event-stream'
