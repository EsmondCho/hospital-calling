"""Integration tests for the read-only chain keyword backoffice endpoint."""

from __future__ import annotations

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


@pytest.fixture
def client() -> Client:
    return Client()


def test_list_returns_seeded_rows(client: Client) -> None:
    response = client.get('/backoffice/chain_keywords/')
    assert response.status_code == 200
    data = response.json()
    # Unpaginated — a plain array, not a {results: ...} envelope.
    assert isinstance(data, list)
    assert len(data) == 20
    first = data[0]
    for key in ['chain_brand_normalized', 'regex_pattern', 'service_tags',
                'ownership', 'match_priority']:
        assert key in first


def test_list_ordered_by_match_priority(client: Client) -> None:
    response = client.get('/backoffice/chain_keywords/')
    data = response.json()
    priorities = [row['match_priority'] for row in data]
    assert priorities == sorted(priorities)
    # vca has the lowest priority (10) → first row.
    assert data[0]['chain_brand_normalized'] == 'vca'


def test_list_is_open_without_token(client: Client) -> None:
    # GET is a safe method — no X-Backoffice-Token required.
    response = client.get('/backoffice/chain_keywords/')
    assert response.status_code == 200
