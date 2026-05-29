"""Integration tests for the backoffice prompt endpoints.

Covers the aggregate logical-prompt list, version auto-bump on create, the
`versions/?name=` listing, free-form (non-slug) names, and the absence of the
dropped `is_active` / `language` fields.

Run: `env=test make test tests/integration/test_backoffice_prompts.py`
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from prompt.models import Prompt

TOKEN = 'test-token-deadbeef'

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture(autouse=True)
def _backoffice_token(settings):
    settings.BACKOFFICE_API_TOKEN = TOKEN


# ── GET /backoffice/prompts/ — aggregate logical-prompt list ────────────────


def test_list_returns_one_entry_per_logical_prompt(api_client):
    Prompt.objects.create(name='alpha', version=1, body='a1')
    Prompt.objects.create(name='alpha', version=2, body='a2')
    Prompt.objects.create(name='beta', version=1, body='b1')

    response = api_client.get('/backoffice/prompts/')
    assert response.status_code == 200
    data = response.json()
    # Unpaginated — a plain array, not a {results: ...} envelope.
    assert isinstance(data, list)

    rows = {row['name']: row for row in data}
    assert rows['alpha']['version_count'] == 2
    assert rows['alpha']['latest_version'] == 2
    assert rows['beta']['version_count'] == 1
    assert rows['beta']['latest_version'] == 1
    # The dropped fields must not surface anywhere in the aggregate row.
    for row in data:
        assert 'is_active' not in row
        assert 'language' not in row


def test_list_excludes_soft_deleted_versions(api_client):
    Prompt.objects.create(name='gamma', version=1, body='g1')
    Prompt.objects.create(
        name='gamma', version=2, body='g2', is_deleted=True
    )

    response = api_client.get('/backoffice/prompts/')
    rows = {row['name']: row for row in response.json()}
    assert rows['gamma']['version_count'] == 1
    assert rows['gamma']['latest_version'] == 1


# ── POST /backoffice/prompts/ — create with version auto-bump ───────────────


def test_create_first_version_starts_at_one(api_client):
    response = api_client.post(
        '/backoffice/prompts/',
        {'name': 'fresh', 'body': 'v1 body'},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 201, response.content
    payload = response.json()
    assert payload['version'] == 1
    assert 'is_active' not in payload
    assert 'language' not in payload


def test_create_second_version_auto_bumps(api_client):
    Prompt.objects.create(name='bumpy', version=1, body='v1 body')
    response = api_client.post(
        '/backoffice/prompts/',
        {
            'name': 'bumpy',
            'body': 'v2 body',
        },
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 201, response.content
    payload = response.json()
    assert payload['version'] == 2
    assert Prompt.objects.filter(name='bumpy').count() == 2


@pytest.mark.parametrize(
    'name',
    [
        'referral policy with spaces',
        '병원 추천 정책',
        'Mixed 한글 and spaces v2',
    ],
)
def test_create_accepts_free_form_names(api_client, name):
    """`name` is a free-form `CharField` — spaces and non-ASCII are allowed."""
    response = api_client.post(
        '/backoffice/prompts/',
        {'name': name, 'body': 'free-form body'},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 201, response.content
    payload = response.json()
    assert payload['name'] == name
    assert payload['version'] == 1


def test_create_requires_name(api_client):
    response = api_client.post(
        '/backoffice/prompts/',
        {'body': 'no name body'},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 400, response.content
    assert 'name' in response.json()


# ── GET /backoffice/prompts/versions/?name= ─────────────────────────────────


def test_versions_endpoint_lists_all_versions_newest_first(api_client):
    Prompt.objects.create(name='delta', version=1, body='d1')
    Prompt.objects.create(name='delta', version=2, body='d2')
    Prompt.objects.create(name='delta', version=3, body='d3')

    response = api_client.get('/backoffice/prompts/versions/', {'name': 'delta'})
    assert response.status_code == 200
    data = response.json()
    # Unpaginated plain array, -version order.
    assert isinstance(data, list)
    assert [row['version'] for row in data] == [3, 2, 1]
    # The versions serializer includes `body`.
    assert data[0]['body'] == 'd3'
    for row in data:
        assert 'is_active' not in row
        assert 'language' not in row


def test_versions_endpoint_excludes_soft_deleted(api_client):
    Prompt.objects.create(name='epsilon', version=1, body='e1')
    Prompt.objects.create(
        name='epsilon',
        version=2,
        body='e2',
        is_deleted=True,
    )

    response = api_client.get(
        '/backoffice/prompts/versions/', {'name': 'epsilon'}
    )
    assert response.status_code == 200
    assert [row['version'] for row in response.json()] == [1]


def test_versions_endpoint_handles_free_form_name(api_client):
    name = '병원 추천 정책'
    Prompt.objects.create(name=name, version=1, body='v1')
    Prompt.objects.create(name=name, version=2, body='v2')

    response = api_client.get('/backoffice/prompts/versions/', {'name': name})
    assert response.status_code == 200
    assert [row['version'] for row in response.json()] == [2, 1]


def test_versions_endpoint_requires_name(api_client):
    response = api_client.get('/backoffice/prompts/versions/')
    assert response.status_code == 400
    assert 'name' in response.json()


# ── GET /backoffice/prompts/<id>/ — single version detail ───────────────────


def test_detail_returns_single_version_without_dropped_fields(api_client):
    prompt = Prompt.objects.create(name='zeta', version=1, body='z1')
    response = api_client.get(f'/backoffice/prompts/{prompt.id}/')
    assert response.status_code == 200
    payload = response.json()
    assert payload['id'] == prompt.id
    assert payload['body'] == 'z1'
    assert 'is_active' not in payload
    assert 'language' not in payload
