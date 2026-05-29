"""Boundary-level tests for the Google Places v1 client.

Mocks `httpx.request` (the single point the client uses) and verifies the
parsing / FieldMask / error-translation behavior that's easy to break.
Per testing.md we mock the outer boundary, not the inner httpx primitives.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import httpx
import pytest

from services.external.google_places.client import (
    GooglePlacesClient,
    GooglePlacesError,
    _ENTERPRISE_FIELD_MASK,
    _PLACE_DETAILS_FIELD_MASK,
)


_VIEWPORT = {'south': 37.0, 'west': -122.5, 'north': 37.5, 'east': -122.0}


def _fake_response(status: int, body: dict | None) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status
    response.json.return_value = body or {}
    if status >= 400:
        request = MagicMock(spec=httpx.Request)
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            f'{status}', request=request, response=response,
        )
    else:
        response.raise_for_status.return_value = None
    return response


def test_search_vet_hospitals_parses_response(mocker) -> None:
    mocker.patch(
        'httpx.request',
        return_value=_fake_response(200, {
            'places': [{'id': 'place_a'}, {'id': 'place_b'}],
            'nextPageToken': 'TOKEN123',
        }),
    )
    client = GooglePlacesClient(api_key='test-key')

    places, next_token, cost = client.search_vet_hospitals(viewport=_VIEWPORT)

    assert [p['id'] for p in places] == ['place_a', 'place_b']
    assert next_token == 'TOKEN123'
    assert cost == Decimal('0.035')


def _mock_request(mocker, response_body: dict) -> dict:
    """Mock `GooglePlacesClient._request` — the module boundary (testing.md /
    plan §5) — capturing the call kwargs so a test can assert the request
    body (`json=`) and field mask without driving httpx internals."""

    captured: dict = {}

    def _capture(method, path, *, json=None, field_mask):
        captured.update(
            method=method, path=path, json=json, field_mask=field_mask,
        )
        return response_body

    mocker.patch.object(GooglePlacesClient, '_request', side_effect=_capture)
    return captured


def test_search_vet_hospitals_sends_location_restriction_rectangle(mocker) -> None:
    """The tile bbox must go out as `locationRestriction.rectangle` (a hard
    boundary), low=SW / high=NE — never `locationBias.circle`."""

    captured = _mock_request(mocker, {'places': [], 'nextPageToken': None})
    GooglePlacesClient(api_key='k').search_vet_hospitals(viewport=_VIEWPORT)

    body = captured['json']
    assert 'locationBias' not in body
    rectangle = body['locationRestriction']['rectangle']
    assert rectangle['low'] == {'latitude': 37.0, 'longitude': -122.5}
    assert rectangle['high'] == {'latitude': 37.5, 'longitude': -122.0}
    assert body['includedType'] == 'veterinary_care'
    # textQuery carries no city name — the rectangle constrains the area.
    assert body['textQuery'] == 'veterinary clinic'
    assert captured['field_mask'] == _ENTERPRISE_FIELD_MASK


def test_search_vet_hospitals_sends_page_token_when_provided(mocker) -> None:
    captured = _mock_request(mocker, {'places': [], 'nextPageToken': None})
    GooglePlacesClient(api_key='k').search_vet_hospitals(
        viewport=_VIEWPORT, page_token='PAGE2',
    )
    assert captured['method'] == 'POST'
    assert captured['path'] == '/places:searchText'
    assert captured['json']['pageToken'] == 'PAGE2'


def test_search_returns_no_next_page_token_when_absent(mocker) -> None:
    mocker.patch('httpx.request', return_value=_fake_response(200, {'places': []}))
    _, next_token, _ = GooglePlacesClient(api_key='k').search_vet_hospitals(
        viewport=_VIEWPORT,
    )
    assert next_token is None


def test_resolve_city_viewport_returns_bbox(mocker) -> None:
    captured = _mock_request(mocker, {
        'places': [{
            'viewport': {
                'low': {'latitude': 33.7, 'longitude': -118.7},
                'high': {'latitude': 34.3, 'longitude': -118.1},
            },
        }],
    })
    viewport = GooglePlacesClient(api_key='k').resolve_city_viewport(
        city='Los Angeles', state_code='CA',
    )
    assert viewport == {
        'south': 33.7, 'west': -118.7, 'north': 34.3, 'east': -118.1,
    }
    assert captured['json']['textQuery'] == 'Los Angeles, CA'
    # No type filter on the city-resolution call.
    assert 'includedType' not in captured['json']


def test_resolve_city_viewport_returns_none_when_no_results(mocker) -> None:
    _mock_request(mocker, {'places': []})
    viewport = GooglePlacesClient(api_key='k').resolve_city_viewport(
        city='Nowheresville', state_code='ZZ',
    )
    assert viewport is None


def test_resolve_city_viewport_returns_none_when_viewport_missing(mocker) -> None:
    _mock_request(mocker, {'places': [{'displayName': {'text': 'X'}}]})
    viewport = GooglePlacesClient(api_key='k').resolve_city_viewport(
        city='Somewhere', state_code='CA',
    )
    assert viewport is None


def test_resolve_city_viewport_returns_none_when_coordinate_missing(mocker) -> None:
    """A partial `viewport` payload (missing one coordinate) resolves to None
    instead of raising KeyError."""

    _mock_request(mocker, {
        'places': [{
            'viewport': {
                'low': {'latitude': 33.7},   # longitude absent
                'high': {'latitude': 34.3, 'longitude': -118.1},
            },
        }],
    })
    viewport = GooglePlacesClient(api_key='k').resolve_city_viewport(
        city='Partial', state_code='CA',
    )
    assert viewport is None


def test_resolve_city_viewport_returns_none_when_box_inverted(mocker) -> None:
    """A topologically invalid box (low above high) is rejected, not handed
    downstream as a corrupt tile rectangle."""

    _mock_request(mocker, {
        'places': [{
            'viewport': {
                'low': {'latitude': 34.3, 'longitude': -118.1},   # north of high
                'high': {'latitude': 33.7, 'longitude': -118.7},
            },
        }],
    })
    viewport = GooglePlacesClient(api_key='k').resolve_city_viewport(
        city='Inverted', state_code='CA',
    )
    assert viewport is None


def test_get_place_details_uses_singular_field_mask(mocker) -> None:
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return _fake_response(200, {'id': 'place_a', 'displayName': {'text': 'X'}})

    mocker.patch('httpx.request', side_effect=_capture)
    GooglePlacesClient(api_key='k').get_place_details('place_a')

    assert captured['method'] == 'GET'
    assert captured['url'].endswith('/places/place_a')
    # Singular response: no `places.` prefix, no `nextPageToken`.
    mask = captured['headers']['X-Goog-FieldMask']
    assert 'places.' not in mask
    assert 'nextPageToken' not in mask
    assert mask == _PLACE_DETAILS_FIELD_MASK


def test_enterprise_field_mask_includes_viewport() -> None:
    """`places.viewport` must be in the mask so search results can also be
    used for viewport resolution."""

    assert 'places.viewport' in _ENTERPRISE_FIELD_MASK
    # The derived singular mask carries the prefix-stripped form.
    assert 'viewport' in _PLACE_DETAILS_FIELD_MASK


def test_error_response_wraps_to_google_places_error(mocker) -> None:
    mocker.patch(
        'httpx.request',
        return_value=_fake_response(
            403,
            {'error': {'code': 403, 'message': 'API key invalid'}},
        ),
    )
    with pytest.raises(GooglePlacesError) as exc_info:
        GooglePlacesClient(api_key='bad').search_vet_hospitals(viewport=_VIEWPORT)
    assert exc_info.value.status_code == 403
    assert 'API key invalid' in exc_info.value.message


def test_error_response_without_json_body_falls_back_to_str(mocker) -> None:
    response = MagicMock(spec=httpx.Response)
    response.status_code = 500
    response.json.side_effect = ValueError('not json')
    request = MagicMock(spec=httpx.Request)
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        'boom', request=request, response=response,
    )
    mocker.patch('httpx.request', return_value=response)

    with pytest.raises(GooglePlacesError) as exc_info:
        GooglePlacesClient(api_key='k').get_place_details('place_x')
    assert exc_info.value.status_code == 500
