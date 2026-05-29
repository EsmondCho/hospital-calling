"""Backoffice REST + SSE for the hospital sourcing pipeline (DRT-5204 §2).

Endpoints:
  POST /backoffice/sourcing/jobs/                  — trigger a new job
  GET  /backoffice/sourcing/jobs/                  — paginated list
  GET  /backoffice/sourcing/jobs/<id>/             — detail
  POST /backoffice/sourcing/jobs/<id>/cancel/      — cancel (status → CANCELLED)
  GET  /backoffice/sourcing/jobs/<id>/events/      — text/event-stream progress
  GET  /backoffice/sourcing/states/                — states with hospital counts
  GET  /backoffice/sourcing/cities/                — cities in a state

The SSE endpoint polls the DB and yields the current row state every
`_SSE_POLL_INTERVAL_SECONDS` until the job hits a terminal status. We
poll the DB rather than wire up Channels/Redis pub-sub because (a)
Django dev/prod stays single-process per request and (b) the UI only
needs ~2-second freshness.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from typing import Any, Generator

import structlog
from django.conf import settings
from django.db.models import Count
from django.http import StreamingHttpResponse
from rest_framework import generics, status
from rest_framework.exceptions import APIException, NotFound
from rest_framework.renderers import BaseRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from hospital.models import Hospital
from services.internal.sourcing.service import (
    SourcingAlreadyRunning,
    SourcingJobNotFound,
    SourcingService,
)
from sourcing.models import City, SourcingJob
from sourcing.vars import SourcingJobStatus, TERMINAL_STATUSES

from ..pagination import BackofficePageNumberPagination
from ..permissions import TokenForUnsafeMethodsMixin
from .serializers import (
    SourcingJobLv1Serializer,
    SourcingJobLv2Serializer,
    SourcingJobTriggerSerializer,
)

logger = structlog.get_logger(__name__)

_SSE_POLL_INTERVAL_SECONDS = 2.0
# Hard cap on how long the SSE connection stays open. A stuck job won't keep
# a worker thread alive indefinitely — the client reconnects via EventSource.
# Sourced from settings so it's tunable per environment (DRT-5265 §4.6.3).
_SSE_MAX_DURATION_SECONDS = settings.SOURCING_SSE_MAX_SECONDS


class SourcingAlreadyRunningError(APIException):
    """409 — duplicate trigger for the same `(state_code, city)` region."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = 'Sourcing job already running for this region.'
    default_code = 'sourcing_already_running'


class SourcingJobListCreateView(TokenForUnsafeMethodsMixin, generics.ListCreateAPIView):
    # Page-number pagination doesn't impose ordering, so order explicitly
    # (newest first, id tiebreak for a stable page split).
    queryset = SourcingJob.objects.all().order_by('-created_at', '-id')
    pagination_class = BackofficePageNumberPagination

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return SourcingJobTriggerSerializer
        return SourcingJobLv1Serializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        triggered_by = getattr(request.user, 'id', None) if getattr(
            request, 'user', None
        ) and request.user.is_authenticated else None

        try:
            job = SourcingService().trigger_job(
                triggered_by_id=triggered_by,
                state_code=data['state_code'],
                city=data['city'],
                max_depth=data['max_depth'],
                call_limit=data['call_limit'],
            )
        except SourcingAlreadyRunning as e:
            raise SourcingAlreadyRunningError(
                detail=f'Sourcing job already running for {e.state_code}/{e.city or "*"}',
            ) from e

        return Response(
            SourcingJobLv2Serializer(job).data, status=status.HTTP_201_CREATED,
        )


class SourcingJobDetailView(TokenForUnsafeMethodsMixin, generics.RetrieveAPIView):
    queryset = SourcingJob.objects.all()
    serializer_class = SourcingJobLv2Serializer


class SourcingJobCancelView(TokenForUnsafeMethodsMixin, APIView):
    def post(self, request, pk: int):
        try:
            job = SourcingService().cancel_job(pk)
        except SourcingJobNotFound as e:
            raise NotFound(f'SourcingJob {pk} not found') from e
        return Response(SourcingJobLv2Serializer(job).data)


class ServerSentEventRenderer(BaseRenderer):
    """Exists so DRF content negotiation accepts an `Accept: text/event-stream`
    request (the media type browser `EventSource` clients always send).

    The SSE view returns a `StreamingHttpResponse` directly, so `render()`
    is bypassed on the success path — but DRF's exception handler still
    calls it to serialize an error response, so `render()` must emit bytes.
    """

    media_type = 'text/event-stream'
    format = 'event-stream'

    def render(
        self,
        data: Any,
        accepted_media_type: str | None = None,
        renderer_context: Mapping[str, Any] | None = None,
    ) -> bytes:
        # Not hit on the success path, but DRF *does* call this to render an
        # error response (e.g. a 404 for a missing job). Returning a non-bytes
        # value there corrupts the body — Django would iterate a dict into its
        # keys — so always emit bytes.
        if data is None:
            return b''
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        if isinstance(data, str):
            return data.encode('utf-8')
        return json.dumps(data, default=str).encode('utf-8')


class SourcingJobEventsView(APIView):
    """Server-Sent Events progress stream.

    Polls `SourcingJob` every 2s and emits a `data: {json}\\n\\n` frame
    whenever any field changed since the last poll, plus a closing `done`
    event on terminal status.

    The endpoint is open to GETs (the `SAFE_METHODS` permission applies
    via `TokenForUnsafeMethodsMixin` elsewhere — here we keep the proxy
    free because Vercel's basic-auth wall already gates the URL).

    `renderer_classes` is pinned to `ServerSentEventRenderer`: the global
    `JSONRenderer`-only config makes DRF reject the SSE `Accept` header
    with 406 during content negotiation, before `get()` ever runs.
    """

    renderer_classes = [ServerSentEventRenderer]

    def get(self, request, pk: int):
        if not SourcingJob.objects.filter(pk=pk).exists():
            raise NotFound(f'SourcingJob {pk} not found')

        response = StreamingHttpResponse(
            _job_event_stream(pk),
            content_type='text/event-stream',
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'   # tell Nginx-style proxies to flush
        return response


def _job_event_stream(job_id: int) -> Generator[bytes, None, None]:
    """Yield SSE frames until the job hits a terminal status or the
    connection's max-duration timer fires."""

    started_at = time.monotonic()
    last_payload: str | None = None

    while True:
        try:
            job = SourcingJob.objects.get(pk=job_id)
        except SourcingJob.DoesNotExist:
            yield b'event: error\ndata: {"error": "job_missing"}\n\n'
            return

        payload = json.dumps(SourcingJobLv2Serializer(job).data, default=str)
        if payload != last_payload:
            yield f'data: {payload}\n\n'.encode('utf-8')
            last_payload = payload

        if job.status in TERMINAL_STATUSES:
            yield b'event: done\ndata: {}\n\n'
            return

        if time.monotonic() - started_at >= _SSE_MAX_DURATION_SECONDS:
            yield b'event: timeout\ndata: {}\n\n'
            return

        time.sleep(_SSE_POLL_INTERVAL_SECONDS)


_STATE_CODE_RE = re.compile(r'^[A-Z]{2}$')


class SourcingStatesView(APIView):
    """States with at least one non-deleted Hospital, each with its row
    count — feeds the sourcing form's state dropdown so an operator only
    sees states we actually have data for. Unpaginated: 50-state ceiling.
    """

    def get(self, request) -> Response:
        # `Hospital.state` is free-form text — the sourcing pipeline writes
        # an uppercase 2-letter code, but a manual entry might not. Fold
        # case in Python so `ca` and `CA` collapse into one dropdown row.
        counts: dict[str, int] = {}
        rows = (
            Hospital.objects.filter(is_deleted=False)
            .values('state')
            .annotate(hospital_count=Count('id'))
        )
        for row in rows:
            state = (row['state'] or '').strip().upper()
            if not state:
                continue
            counts[state] = counts.get(state, 0) + row['hospital_count']
        return Response([
            {'state_code': state, 'hospital_count': counts[state]}
            for state in sorted(counts)
        ])


def _city_match_keys(city_name: str) -> list[str]:
    """Lowercased forms a `City` reference name can take in the free-text
    `Hospital.city` / `SourcingJob.city` columns.

    The `city` table holds US Census incorporated-place names, which often
    carry a ` City` / ` Town` suffix that Google Places' locality drops —
    Census `Boise City` vs Google `Boise`. Matching the suffix-stripped
    form too reconciles the two. (`Oklahoma City` etc. stay correct: Google
    also returns `Oklahoma City`, so the exact-match key still hits.)

    Assumes no state lists both `X` and `X City` as distinct dropdown
    cities — true for the Census place set.
    """

    low = city_name.lower()
    keys = [low]
    for suffix in (' city', ' town'):
        if low.endswith(suffix) and len(low) > len(suffix):
            keys.append(low[: -len(suffix)])
    return keys


class SourcingCitiesView(APIView):
    """Every `City` in a state, annotated with how many non-deleted
    hospitals sit in it and whether a sourcing job has already run it —
    feeds the sourcing form's city dropdown. Unpaginated: a state has at
    most a few thousand cities and the UI searches the list locally.
    """

    def get(self, request) -> Response:
        state = request.query_params.get('state') or ''
        if not _STATE_CODE_RE.match(state):
            return Response(
                {'detail': 'Query param `state` is required and must be a 2-letter uppercase code.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Sort case-insensitively in Python — leaning on the DB's ORDER BY
        # would couple the dropdown order to the server's LC_COLLATE.
        # `.order_by()` drops City.Meta.ordering: that DB sort is dead work
        # since the Python re-sort below supersedes it.
        city_names = sorted(
            City.objects.filter(state_code=state)
            .order_by()
            .values_list('name', flat=True),
            key=str.lower,
        )

        # One aggregate per related table, then join in Python on the
        # lowercased city name — a query per city would be ~thousands of
        # round-trips. Hospital.city / SourcingJob.city are free-form text,
        # so two raw strings can lowercase-collide; accumulate on collision.
        # `Hospital.state` is free-form too — match it case-insensitively.
        hospital_counts: dict[str, int] = {}
        hospital_rows = (
            Hospital.objects.filter(is_deleted=False, state__iexact=state)
            .values('city')
            .annotate(hospital_count=Count('id'))
        )
        for row in hospital_rows:
            city = row['city']
            if not city:
                continue
            hospital_counts[city.lower()] = (
                hospital_counts.get(city.lower(), 0) + row['hospital_count']
            )

        # `sourced` = a job actually finished collecting this city. A
        # FAILED / CANCELLED / in-flight job doesn't count — the operator
        # still needs to source it. `.distinct()` drops duplicate rows when
        # a city has several completed jobs.
        sourced_cities = {
            city.lower()
            for city in SourcingJob.objects.filter(
                state_code=state, status=SourcingJobStatus.COMPLETED,
            )
            .values_list('city', flat=True)
            .distinct()
            if city
        }

        # Match each City row against the free-text hospital / job city on
        # the raw name *and* its Census-suffix-stripped form (see
        # `_city_match_keys`) — `Boise City` must count `Boise` hospitals.
        result: list[dict] = []
        for name in city_names:
            keys = _city_match_keys(name)
            result.append({
                'name': name,
                'hospital_count': sum(hospital_counts.get(key, 0) for key in keys),
                'sourced': any(key in sourced_cities for key in keys),
            })
        return Response(result)
