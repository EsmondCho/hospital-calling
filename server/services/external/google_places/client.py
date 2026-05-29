"""Google Places (New v1) HTTP client.

Used by the hospital sourcing pipeline (DRT-5204 §2). Speaks the v1 REST
shape — Text Search + Place Details. Text Search backs both vet-hospital
discovery and city-viewport resolution.

Convention: FieldMask is set per-request and drives the SKU price tier.
The default `_ENTERPRISE_FIELD_MASK` covers the full set the sourcing
pipeline needs (name, address, location, types, phone, website, rating,
hours, timezone) in a single Enterprise-SKU call — ~$0.035/1k vs
~$0.105/1k if details are split out.

ToS note (DRT-5204 §B5 / §8.1): `place_id` is the only field allowed
for indefinite storage. Other fields are kept on Hospital rows under
the "90-day staleness refresh" policy documented in the research log.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
import structlog
from django.conf import settings

from utils.cache_utils import function_cache

logger = structlog.get_logger(__name__)


class GooglePlacesError(Exception):
    """Raised for non-2xx responses from Google Places."""

    def __init__(self, status_code: int, message: str, details: dict[str, Any] | None = None):
        self.status_code = status_code
        self.message = message
        self.details = details or {}
        super().__init__(f'GooglePlacesError {status_code}: {message}')


# Enterprise SKU field set: enough metadata to classify without a follow-up
# Place Details call. Atmosphere fields (reviews / editorialSummary) are
# intentionally excluded — they bump the SKU to $40/1k.
_ENTERPRISE_FIELD_MASK = ','.join([
    'places.id',
    'places.displayName',
    'places.formattedAddress',
    'places.addressComponents',
    'places.location',
    'places.types',
    'places.primaryType',
    'places.businessStatus',
    'places.nationalPhoneNumber',
    'places.internationalPhoneNumber',
    'places.websiteUri',
    'places.rating',
    'places.userRatingCount',
    'places.currentOpeningHours',
    'places.timeZone',
    'places.utcOffsetMinutes',
    'places.viewport',
    'nextPageToken',
])

# Place Details (`GET /places/{id}`) returns a Place directly, not a `places`
# array — strip the `places.` prefix and drop `nextPageToken` (singular
# response has no pagination). Computed at import time so reordering
# `_ENTERPRISE_FIELD_MASK` never silently produces a malformed mask.
_PLACE_DETAILS_FIELD_MASK = ','.join(
    f.removeprefix('places.')
    for f in _ENTERPRISE_FIELD_MASK.split(',')
    if f and f != 'nextPageToken'
)

# Per-request approximate cost — Enterprise SKU, regardless of result count.
_TEXT_SEARCH_COST_USD = Decimal('0.035')


@function_cache(minutes=60)
def get_client() -> 'GooglePlacesClient':
    return GooglePlacesClient(
        api_key=settings.GOOGLE_PLACES_API_KEY,
    )


class GooglePlacesClient:
    BASE_URL = 'https://places.googleapis.com/v1'

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self, field_mask: str) -> dict[str, str]:
        return {
            'Content-Type': 'application/json',
            'X-Goog-Api-Key': self.api_key,
            'X-Goog-FieldMask': field_mask,
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        field_mask: str,
    ) -> dict[str, Any]:
        url = f'{self.BASE_URL}{path}'
        try:
            response = httpx.request(
                method=method,
                url=url,
                headers=self._headers(field_mask),
                json=json,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            payload: dict[str, Any]
            try:
                payload = e.response.json()
            except Exception:
                payload = {}
            message = (payload.get('error') or {}).get('message') if isinstance(payload, dict) else None
            raise GooglePlacesError(
                status_code=e.response.status_code,
                message=message or str(e),
                details=payload,
            ) from e

    def search_vet_hospitals(
        self,
        *,
        viewport: dict[str, float],
        page_token: str | None = None,
        page_size: int = 20,
        field_mask: str = _ENTERPRISE_FIELD_MASK,
    ) -> tuple[list[dict[str, Any]], str | None, Decimal]:
        """Text Search for vet candidates inside a rectangular tile.

        `viewport` is a `{'south', 'west', 'north', 'east'}` bounding box
        sent as `locationRestriction.rectangle` — a hard boundary, unlike
        `locationBias`, so quadtree tiles don't bleed adjacent results
        (research §Q1). `textQuery` carries no city name; the rectangle
        alone constrains the area.

        Returns `(places, next_page_token, cost_usd)`. `next_page_token`
        is None on the final page. `cost_usd` is the approximate SKU cost
        for this single request (the caller accumulates it).
        """

        body: dict[str, Any] = {
            'textQuery': 'veterinary clinic',
            'includedType': 'veterinary_care',
            'pageSize': page_size,
            'locationRestriction': {
                'rectangle': {
                    'low': {
                        'latitude': viewport['south'],
                        'longitude': viewport['west'],
                    },
                    'high': {
                        'latitude': viewport['north'],
                        'longitude': viewport['east'],
                    },
                },
            },
        }
        if page_token:
            body['pageToken'] = page_token

        data = self._request('POST', '/places:searchText', json=body, field_mask=field_mask)
        places = data.get('places') or []
        next_page_token = data.get('nextPageToken')
        logger.info(
            'google_places.search_vet_hospitals',
            count=len(places),
            has_next_page=bool(next_page_token),
        )
        return places, next_page_token, _TEXT_SEARCH_COST_USD

    def resolve_city_viewport(
        self, *, city: str, state_code: str,
    ) -> dict[str, float] | None:
        """Resolve a city's locality viewport via `searchText`.

        Sends `"{city}, {state}"` with no type filter and reads the first
        result's `viewport` (research §Q5 path B). Returns a
        `{'south', 'west', 'north', 'east'}` box, or None when the city
        can't be resolved.
        """

        body = {'textQuery': f'{city}, {state_code}'}
        data = self._request(
            'POST', '/places:searchText', json=body,
            field_mask='places.viewport,places.displayName',
        )
        places = data.get('places') or []
        if not places:
            return None
        viewport = places[0].get('viewport') or {}
        low = viewport.get('low') or {}
        high = viewport.get('high') or {}

        # Read each coordinate defensively — a partial `viewport` payload
        # would otherwise raise KeyError.
        south = low.get('latitude')
        west = low.get('longitude')
        north = high.get('latitude')
        east = high.get('longitude')
        if None in (south, west, north, east):
            return None

        # Topology + range sanity check: low must be the SW corner, high the
        # NE corner, both inside valid lat/lon bounds. A malformed box would
        # silently corrupt every downstream tile rectangle.
        if not (
            -90 <= south < north <= 90
            and -180 <= west < east <= 180
        ):
            logger.warning(
                'google_places.resolve_city_viewport.invalid_box',
                city=city, state_code=state_code,
                south=south, west=west, north=north, east=east,
            )
            return None

        return {
            'south': south,
            'west': west,
            'north': north,
            'east': east,
        }

    def get_place_details(
        self,
        place_id: str,
        *,
        field_mask: str = _PLACE_DETAILS_FIELD_MASK,
    ) -> dict[str, Any]:
        """Lookup full details for a single Place ID."""

        data = self._request('GET', f'/places/{place_id}', field_mask=field_mask)
        logger.info('google_places.get_place_details', place_id=place_id)
        return data
