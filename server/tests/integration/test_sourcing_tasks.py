"""Integration tests for the sourcing tile fan-out pipeline (DRT-5265 §5.2).

The Google Places client is mocked at the module level (per testing.md —
never mock httpx internals). Celery enqueue is driven synchronously: every
task's `apply_async` is patched to call the task inline so the full
fetch → classify → persist → split → finalize chain runs in one process,
in deterministic order.

`HospitalClassifier` is mocked at the boundary so persist runs without the
real Anthropic call.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from django.db import transaction

# `classify_batch` imports the classifier lazily, so the submodule is not
# registered on `services.internal.sourcing` when the `run_pipeline_inline`
# fixture's `mocker.patch(...classifier.HospitalClassifier)` resolves its
# target — a plain import here registers it.
import services.internal.sourcing.classifier  # noqa: F401
from hospital.models import Hospital
from hospital.vars import HospitalSource
from services.internal.sourcing import tasks as sourcing_tasks
from sourcing.models import SourcingJob, SourcingTile
from sourcing.vars import (
    PartialReason,
    SourcingJobStatus,
    SourcingTileStatus,
)

# ──────────────────────────────────────────────────────────────────────────
# Test doubles
# ──────────────────────────────────────────────────────────────────────────

class FakeGooglePlacesClient:
    """Scripts `search_vet_hospitals` per (tile rectangle) call.

    `pages` is a list of `(places, next_page_token)` tuples consumed in
    order — one entry per `search_vet_hospitals` invocation. `viewport_kind`
    lets a test branch the script by tile size for the split-recursion case.
    """

    def __init__(self, pages: list[tuple[list[dict], str | None]]) -> None:
        self._pages = list(pages)
        self.calls: list[dict] = []

    def search_vet_hospitals(self, *, viewport, page_token=None, **_kw):
        self.calls.append({'viewport': dict(viewport), 'page_token': page_token})
        if not self._pages:
            return [], None, Decimal('0.035')
        places, next_token = self._pages.pop(0)
        return list(places), next_token, Decimal('0.035')

    def resolve_city_viewport(self, *, city, state_code):
        return {'south': 0.0, 'west': 0.0, 'north': 1.0, 'east': 1.0}


class _PlacesByViewport:
    """Routes `search_vet_hospitals` by the tile's area so a recursive split
    can hand children fewer results than the (capped) parent."""

    def __init__(self, big_pages, small_pages) -> None:
        self._big = list(big_pages)
        self._small = list(small_pages)
        self.calls: list[dict] = []

    def search_vet_hospitals(self, *, viewport, page_token=None, **_kw):
        self.calls.append({'viewport': dict(viewport), 'page_token': page_token})
        area = (viewport['north'] - viewport['south']) * (viewport['east'] - viewport['west'])
        script = self._big if area >= 0.25 else self._small
        if not script:
            return [], None, Decimal('0.035')
        places, next_token = script.pop(0)
        return list(places), next_token, Decimal('0.035')

    def resolve_city_viewport(self, *, city, state_code):
        return {'south': 0.0, 'west': 0.0, 'north': 1.0, 'east': 1.0}


class _FakeLLMLabel:
    ownership = 'UNCLASSIFIED'
    service_tags: tuple = ()
    specialty_areas: tuple = ()
    appointment_mode = 'UNKNOWN'
    chain_brand_normalized = None
    reasoning = ''
    needs_review = False
    input_tokens = 0
    output_tokens = 0


class _FakeClassifier:
    def classify(self, raw, rule_label):
        return _FakeLLMLabel()


def _places(count: int, *, prefix: str = 'p') -> list[dict]:
    """`count` minimal Google Place payloads."""

    return [
        {'id': f'{prefix}_{i}', 'displayName': {'text': f'Vet {prefix} {i}'}}
        for i in range(count)
    ]


@pytest.fixture
def run_pipeline_inline(mocker):
    """Patch every sourcing task's `apply_async` so the chain runs inline.

    Returns a callable that drives `start_job` synchronously for a job_id.
    `group(...).apply_async()` in `_split_tile` is also patched to run each
    child `fetch_tile` inline.
    """

    def _inline(task):
        def _apply_async(*, kwargs=None, **_options):
            return task.run(**(kwargs or {}))
        return _apply_async

    for task in (
        sourcing_tasks.start_job,
        sourcing_tasks.resolve_viewport,
        sourcing_tasks.fetch_tile,
        sourcing_tasks.classify_batch,
        sourcing_tasks.persist_batch,
        sourcing_tasks.try_finalize,
    ):
        mocker.patch.object(task, 'apply_async', side_effect=_inline(task))

    # `transaction.on_commit(cb)` callbacks never fire inside the
    # non-committing transaction `@pytest.mark.django_db` wraps each test
    # in. Run them eagerly so the on-commit `try_finalize` / split fan-out
    # enqueues (P1-1 / P2) execute within the inline pipeline.
    mocker.patch(
        'django.db.transaction.on_commit',
        side_effect=lambda func, *_a, **_kw: func(),
    )

    # `group(...).apply_async()` — run each signature's task inline.
    # `sig.type` is the resolved task object; `sig.kwargs` its keyword args.
    class _InlineGroup:
        def __init__(self, signatures):
            self._signatures = list(signatures)

        def apply_async(self, *_a, **_kw):
            for sig in self._signatures:
                sig.type.run(**dict(sig.kwargs))

    mocker.patch.object(sourcing_tasks, 'group', _InlineGroup)

    # Boundary mock for the LLM classifier.
    mocker.patch(
        'services.internal.sourcing.classifier.HospitalClassifier',
        _FakeClassifier,
    )

    def _drive(job_id: int) -> None:
        sourcing_tasks.start_job.run(job_id=job_id)

    return _drive


def _make_job(**overrides) -> SourcingJob:
    defaults: dict[str, Any] = {
        'state_code': 'CA', 'city': 'Los Angeles',
        'status': SourcingJobStatus.PENDING,
        'max_depth': 6, 'call_limit': 300,
    }
    defaults.update(overrides)
    return SourcingJob.objects.create(**defaults)


# ──────────────────────────────────────────────────────────────────────────
# Cap heuristic — exactly 60 / 55-59 / <55
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_cap_exactly_60_splits_root_into_four_children(mocker, run_pipeline_inline):
    """3 pages x 20, last page has no nextPageToken → root SPLIT, 4 PENDING
    children, total_tiles == 5. Children return empty so the job finishes."""

    client = _PlacesByViewport(
        big_pages=[
            (_places(20, prefix='a'), 'TOKEN1'),
            (_places(20, prefix='b'), 'TOKEN2'),
            (_places(20, prefix='c'), None),
        ],
        small_pages=[],   # children find nothing
    )
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client,
    )

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    root = SourcingTile.objects.get(job=job, depth=0)
    assert root.status == SourcingTileStatus.SPLIT
    assert root.fetched_count == 60
    children = SourcingTile.objects.filter(job=job, depth=1)
    assert children.count() == 4
    assert job.total_tiles == 5
    assert job.status == SourcingJobStatus.COMPLETED


@pytest.mark.django_db
def test_cap_57_in_band_splits(mocker, run_pipeline_inline):
    """55-59 band: cumulative 57 with no nextPageToken → conservative split."""

    client = _PlacesByViewport(
        big_pages=[
            (_places(20, prefix='a'), 'TOKEN1'),
            (_places(20, prefix='b'), 'TOKEN2'),
            (_places(17, prefix='c'), None),
        ],
        small_pages=[],
    )
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client,
    )

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    root = SourcingTile.objects.get(job=job, depth=0)
    assert root.status == SourcingTileStatus.SPLIT
    assert root.fetched_count == 57
    assert SourcingTile.objects.filter(job=job, depth=1).count() == 4


@pytest.mark.django_db
def test_below_threshold_completes_without_split(mocker, run_pipeline_inline):
    """Cumulative 30, no nextPageToken → tile COMPLETED, no split,
    total_tiles == 1."""

    client = FakeGooglePlacesClient(pages=[(_places(30), None)])
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client,
    )

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    root = SourcingTile.objects.get(job=job, depth=0)
    assert root.status == SourcingTileStatus.COMPLETED
    assert SourcingTile.objects.filter(job=job).count() == 1
    assert job.total_tiles == 1
    assert job.completed_tiles == 1
    assert job.status == SourcingJobStatus.COMPLETED
    assert job.partial is False


# ──────────────────────────────────────────────────────────────────────────
# Recursive split — children that also cap produce grandchildren
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_recursive_split_produces_grandchildren(mocker, run_pipeline_inline):
    """Root caps → 4 children; the children also cap → grandchildren.
    `depth` increments down the tree."""

    # Tiles at depth 0 (area 1.0) and depth 1 (area 0.25) return a cap;
    # depth 2 (area 0.0625) and smaller return nothing.
    class _AlwaysCapDownTwoLevels:
        def __init__(self):
            self.calls = []

        def search_vet_hospitals(self, *, viewport, page_token=None, **_kw):
            self.calls.append(dict(viewport))
            area = (
                (viewport['north'] - viewport['south'])
                * (viewport['east'] - viewport['west'])
            )
            # Threshold sits strictly between depth-1 area (0.25) and
            # depth-2 area (0.0625), so only depth 0 and depth 1 cap.
            if area >= 0.125:
                return _places(60), None, Decimal('0.035')
            return [], None, Decimal('0.035')

        def resolve_city_viewport(self, *, city, state_code):
            return {'south': 0.0, 'west': 0.0, 'north': 1.0, 'east': 1.0}

    mocker.patch(
        'services.external.google_places.client.get_client',
        return_value=_AlwaysCapDownTwoLevels(),
    )

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    assert SourcingTile.objects.filter(job=job, depth=0).count() == 1
    assert SourcingTile.objects.filter(job=job, depth=1).count() == 4
    # Each of 4 capped children splits into 4 → 16 grandchildren.
    assert SourcingTile.objects.filter(job=job, depth=2).count() == 16
    assert job.total_tiles == 21
    assert job.status == SourcingJobStatus.COMPLETED


# ──────────────────────────────────────────────────────────────────────────
# Minimum-size residual
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_min_size_residual_marks_capped_and_partial(mocker, run_pipeline_inline):
    """A tiny root viewport that still hits the cap → capped_at_min_size,
    job partial with reason min_size_residual."""

    class _TinyViewportClient:
        def search_vet_hospitals(self, *, viewport, page_token=None, **_kw):
            return _places(60), None, Decimal('0.035')

        def resolve_city_viewport(self, *, city, state_code):
            # ~0.001° box ≈ 111m edge — below the 300m floor.
            return {'south': 37.0, 'west': -122.0, 'north': 37.001, 'east': -121.999}

    mocker.patch(
        'services.external.google_places.client.get_client',
        return_value=_TinyViewportClient(),
    )

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    root = SourcingTile.objects.get(job=job, depth=0)
    assert root.status == SourcingTileStatus.COMPLETED
    assert root.capped_at_min_size is True
    assert SourcingTile.objects.filter(job=job).count() == 1   # no split
    assert job.capped_tile_count == 1
    assert job.partial is True
    assert job.partial_reason == PartialReason.MIN_SIZE_RESIDUAL
    assert job.status == SourcingJobStatus.COMPLETED


@pytest.mark.django_db
def test_depth_limit_alone_caps_tile(mocker, run_pipeline_inline):
    """`max_depth=0` stops splitting on depth alone (the viewport is large,
    well above the min-size floor) → root capped, job partial /
    min_size_residual, no children."""

    client = FakeGooglePlacesClient(pages=[(_places(60), None)])
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client,
    )

    # max_depth=0 → root (depth 0) cannot split: `depth < max_depth` is False.
    job = _make_job(max_depth=0)
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    root = SourcingTile.objects.get(job=job, depth=0)
    assert root.status == SourcingTileStatus.COMPLETED
    assert root.capped_at_min_size is True
    # Capped on the depth guardrail, not min-size — but a large 1°x1° box
    # confirms it was depth, not edge length, that stopped the split.
    assert SourcingTile.objects.filter(job=job).count() == 1   # no children
    assert job.capped_tile_count == 1
    assert job.partial is True
    assert job.partial_reason == PartialReason.MIN_SIZE_RESIDUAL
    assert job.status == SourcingJobStatus.COMPLETED


# ──────────────────────────────────────────────────────────────────────────
# Call limit
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_call_limit_stops_search_and_marks_partial(mocker, run_pipeline_inline):
    """call_limit=2: the root caps and splits (2 calls used across its 2
    pages); the children's `fetch_tile` find call_count >= limit, close
    without searching, and the job ends partial / call_limit."""

    client = _PlacesByViewport(
        big_pages=[
            (_places(40, prefix='a'), 'TOKEN1'),
            (_places(20, prefix='b'), None),
        ],
        small_pages=[(_places(5), None)],   # never reached — limit hit first
    )
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client,
    )

    job = _make_job(call_limit=2)
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    # Exactly 2 Google calls: the root's 2 pages. The children never search.
    assert job.call_count == 2
    assert len(client.calls) == 2
    assert job.status == SourcingJobStatus.COMPLETED
    assert job.partial is True
    assert job.partial_reason == PartialReason.CALL_LIMIT
    # Children were created by the split but closed without a search call.
    children = SourcingTile.objects.filter(job=job, depth=1)
    assert children.count() == 4
    assert all(c.status == SourcingTileStatus.COMPLETED for c in children)
    # SPLIT root (1) + 4 call-limited children = every tile resolved, so the
    # progress ratio reaches 100% (completed_tiles == total_tiles).
    assert job.completed_tiles == 5
    assert job.total_tiles == 5


# ──────────────────────────────────────────────────────────────────────────
# Tile failure isolation
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_tile_failure_isolated_job_completes_partial(mocker, run_pipeline_inline):
    """A tile's Google call raising a non-retryable error fails only that
    tile; the job still reaches COMPLETED + partial (tile_failures)."""

    from services.external.google_places.client import GooglePlacesError

    class _FailingClient:
        def search_vet_hospitals(self, *, viewport, page_token=None, **_kw):
            raise GooglePlacesError(status_code=403, message='API key invalid')

        def resolve_city_viewport(self, *, city, state_code):
            return {'south': 0.0, 'west': 0.0, 'north': 1.0, 'east': 1.0}

    mocker.patch(
        'services.external.google_places.client.get_client',
        return_value=_FailingClient(),
    )

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    root = SourcingTile.objects.get(job=job, depth=0)
    assert root.status == SourcingTileStatus.FAILED
    # The raw Google message is normalized to a stable code (P2).
    assert root.error_message == 'upstream_error'
    assert job.failed_tile_count == 1
    # The job itself is NOT failed — only the tile.
    assert job.status == SourcingJobStatus.COMPLETED
    assert job.partial is True
    assert job.partial_reason == PartialReason.TILE_FAILURES


# ──────────────────────────────────────────────────────────────────────────
# OVER_QUERY_LIMIT retry
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_over_query_limit_retries_then_fails(mocker, run_pipeline_inline):
    """429 every time → tile re-enqueued with backoff until retries are
    exhausted, then FAILED with retry_count == SOURCING_TILE_MAX_RETRIES."""

    from django.conf import settings

    from services.external.google_places.client import GooglePlacesError

    class _RateLimitedClient:
        def __init__(self):
            self.call_count = 0

        def search_vet_hospitals(self, *, viewport, page_token=None, **_kw):
            self.call_count += 1
            raise GooglePlacesError(status_code=429, message='RESOURCE_EXHAUSTED')

        def resolve_city_viewport(self, *, city, state_code):
            return {'south': 0.0, 'west': 0.0, 'north': 1.0, 'east': 1.0}

    client = _RateLimitedClient()
    mocker.patch(
        'services.external.google_places.client.get_client',
        return_value=client,
    )
    # `fetch_tile` retries via `apply_async(countdown=...)`; the inline
    # patch ignores countdown and runs immediately, so the retry loop
    # converges within the test.

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    root = SourcingTile.objects.get(job=job, depth=0)
    assert root.status == SourcingTileStatus.FAILED
    assert root.retry_count == settings.SOURCING_TILE_MAX_RETRIES
    # Total Google calls = 1 initial + SOURCING_TILE_MAX_RETRIES retries.
    assert client.call_count == 1 + settings.SOURCING_TILE_MAX_RETRIES
    # The retries reuse the original reserved call slot — `call_count` on the
    # job counts the logical fetch once, not once per retry.
    assert job.call_count == 1
    # Tile carries the normalized error code, not the raw Google text.
    assert root.error_message == 'rate_limited'
    assert job.failed_tile_count == 1
    assert job.status == SourcingJobStatus.COMPLETED
    assert job.partial_reason == PartialReason.TILE_FAILURES


# ──────────────────────────────────────────────────────────────────────────
# Finalize idempotency / race
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_finalize_job_is_idempotent(mocker, run_pipeline_inline):
    """Two `try_finalize` calls racing to the same 'no unresolved tiles'
    conclusion transition the job exactly once."""

    client = FakeGooglePlacesClient(pages=[(_places(10), None)])
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client,
    )

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()
    assert job.status == SourcingJobStatus.COMPLETED
    first_completed_at = job.completed_at

    # A second finalize against the already-COMPLETED job is a no-op.
    result = sourcing_tasks.finalize_job(job_id=job.pk)
    assert result['result'] == 'noop'
    job.refresh_from_db()
    assert job.completed_at == first_completed_at


@pytest.mark.django_db
def test_try_finalize_waits_for_unresolved_tiles(mocker, run_pipeline_inline):
    """`try_finalize` with a PENDING tile still around must not finalize."""

    job = _make_job(status=SourcingJobStatus.RUNNING)
    SourcingTile.objects.create(
        job=job, south=0, west=0, north=1, east=1, depth=0,
        status=SourcingTileStatus.PENDING,
    )

    result = sourcing_tasks.try_finalize(job_id=job.pk)
    assert result['result'] == 'pending_tiles'
    job.refresh_from_db()
    assert job.status == SourcingJobStatus.RUNNING


@pytest.mark.django_db
def test_double_try_finalize_transitions_job_exactly_once():
    """Two `try_finalize` calls against a RUNNING job with zero unresolved
    tiles must transition it to COMPLETED exactly once — the second call's
    `finalize_job.filter(status=RUNNING).update()` matches no rows."""

    job = _make_job(status=SourcingJobStatus.RUNNING)
    SourcingTile.objects.create(
        job=job, south=0, west=0, north=1, east=1, depth=0,
        status=SourcingTileStatus.COMPLETED,
    )

    first = sourcing_tasks.try_finalize(job_id=job.pk)
    second = sourcing_tasks.try_finalize(job_id=job.pk)

    # Exactly one call performs the real RUNNING→COMPLETED transition.
    assert first['result'] == 'completed'
    assert second['result'] == 'skipped'   # job no longer RUNNING on 2nd entry
    job.refresh_from_db()
    assert job.status == SourcingJobStatus.COMPLETED


# ──────────────────────────────────────────────────────────────────────────
# Viewport resolution failure
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_viewport_resolution_failure_fails_job(mocker, run_pipeline_inline):
    """`resolve_city_viewport` returning None is a root-level fatal error →
    job FAILED with a normalized `city_not_found` code, no tiles created."""

    class _NoCityClient:
        def resolve_city_viewport(self, *, city, state_code):
            return None

    mocker.patch(
        'services.external.google_places.client.get_client',
        return_value=_NoCityClient(),
    )

    job = _make_job(city='Nowheresville')
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    assert job.status == SourcingJobStatus.FAILED
    assert job.error_message == 'city_not_found'
    assert job.error_count == 1
    assert SourcingTile.objects.filter(job=job).count() == 0


@pytest.mark.django_db
def test_viewport_resolution_exception_fails_job(mocker, run_pipeline_inline):
    """`resolve_city_viewport` raising is a root-level fatal error → job
    FAILED with the normalized `upstream_error` code, error_count bumped,
    no tiles created."""

    from services.external.google_places.client import GooglePlacesError

    class _RaisingClient:
        def resolve_city_viewport(self, *, city, state_code):
            raise GooglePlacesError(status_code=500, message='internal error')

    mocker.patch(
        'services.external.google_places.client.get_client',
        return_value=_RaisingClient(),
    )

    job = _make_job(city='Boomtown')
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    assert job.status == SourcingJobStatus.FAILED
    assert job.error_message == 'upstream_error'
    assert job.error_count == 1
    assert SourcingTile.objects.filter(job=job).count() == 0


@pytest.mark.django_db
def test_pagination_within_max_pages(mocker, run_pipeline_inline):
    """A tile with 2 pages (< MAX_PAGES) and a sub-threshold total
    paginates then COMPLETEs without a split."""

    client = FakeGooglePlacesClient(pages=[
        (_places(20, prefix='a'), 'TOKEN1'),
        (_places(10, prefix='b'), None),
    ])
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client,
    )

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    root = SourcingTile.objects.get(job=job, depth=0)
    assert root.page_count == 2
    assert root.fetched_count == 30
    assert root.status == SourcingTileStatus.COMPLETED
    assert job.status == SourcingJobStatus.COMPLETED


# ──────────────────────────────────────────────────────────────────────────
# Classify / persist-stage crash isolation
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_classify_crash_fails_tile_instead_of_hanging(mocker, run_pipeline_inline):
    """An unhandled crash in `classify_batch` marks the tile FAILED instead
    of leaving it — and the whole job — stuck in RUNNING. The job still
    finalizes: COMPLETED + partial (tile_failures), like a Google failure."""

    client = FakeGooglePlacesClient(pages=[(_places(10), None)])
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client,
    )

    class _BrokenClassifier:
        def __init__(self, *_a, **_kw):
            raise RuntimeError('classifier unavailable')

    # Override the fixture's boundary mock — constructing the classifier now
    # crashes, mirroring the prod `ModuleNotFoundError: No module named
    # 'anthropic'` that hung a real sourcing job (DRT-5291).
    mocker.patch(
        'services.internal.sourcing.classifier.HospitalClassifier', _BrokenClassifier,
    )

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    root = SourcingTile.objects.get(job=job, depth=0)
    assert root.status == SourcingTileStatus.FAILED
    assert root.error_message == 'pipeline_error'
    assert job.failed_tile_count == 1
    assert job.error_count == 1
    # The crash fails only the tile — the job finalizes, never hangs.
    assert job.status == SourcingJobStatus.COMPLETED
    assert job.partial is True
    assert job.partial_reason == PartialReason.TILE_FAILURES


@pytest.mark.django_db
def test_persist_crash_fails_tile_instead_of_hanging(mocker, run_pipeline_inline):
    """An unhandled crash in `persist_batch` marks the tile FAILED and lets
    the job finalize, instead of leaving the tile stuck in RUNNING."""

    client = FakeGooglePlacesClient(pages=[(_places(10), None)])
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client,
    )

    def _boom(**_kwargs):
        raise RuntimeError('_advance_tile exploded')

    mocker.patch.object(sourcing_tasks, '_advance_tile', _boom)

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    root = SourcingTile.objects.get(job=job, depth=0)
    assert root.status == SourcingTileStatus.FAILED
    assert root.error_message == 'pipeline_error'
    assert job.failed_tile_count == 1
    assert job.error_count == 1
    assert job.status == SourcingJobStatus.COMPLETED
    assert job.partial is True
    assert job.partial_reason == PartialReason.TILE_FAILURES


# ──────────────────────────────────────────────────────────────────────────
# Practice-dedup — per-vet listings merge into one clinic row (DRT-5297)
# ──────────────────────────────────────────────────────────────────────────

def _vet_place(
    place_id: str, name: str, *, phone: str, lat: float, lng: float,
) -> dict:
    """A Google Place payload with a phone + coords for the dedup path."""

    return {
        'id': place_id,
        'displayName': {'text': name},
        'internationalPhoneNumber': phone,
        'location': {'latitude': lat, 'longitude': lng},
        'types': ['veterinary_care', 'point_of_interest'],
        'primaryType': 'veterinary_care',
        'businessStatus': 'OPERATIONAL',
    }


@pytest.mark.django_db
def test_practitioner_listings_merge_into_one_clinic_row(mocker, run_pipeline_inline):
    """A tile returning a clinic place + two practitioner places that share the
    same phone + coords collapses to exactly ONE live Hospital row. The clinic
    name wins over the "Dr." names, both practitioner place_ids land in
    `metadata['member_place_ids']`, and the job's `merged_count` is 2."""

    phone = '+15095551234'
    lat, lng = 40.0, -74.0
    pages = [(
        [
            _vet_place('clinic_pid', 'Starch Pet Hospital', phone=phone, lat=lat, lng=lng),
            _vet_place('vet1_pid', 'Dr. Brian Martz', phone=phone, lat=lat, lng=lng),
            _vet_place('vet2_pid', 'Halligan Lori DVM', phone=phone, lat=lat, lng=lng),
        ],
        None,
    )]
    client = FakeGooglePlacesClient(pages=pages)
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client,
    )

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    rows = Hospital.objects.filter(
        source=HospitalSource.GOOGLE_PLACES, phone_e164=phone, is_deleted=False,
    )
    assert rows.count() == 1
    survivor = rows.first()
    # The clinic listing was persisted first (lowest id) and stays canonical;
    # its name is the clinic name, never a "Dr." practitioner listing.
    assert survivor.name == 'Starch Pet Hospital'
    assert survivor.source_external_id == 'clinic_pid'
    members = survivor.metadata.get('member_place_ids') or []
    assert set(members) == {'vet1_pid', 'vet2_pid'}
    assert job.merged_count == 2
    # Only the clinic row was a real insert; the two practitioners merged.
    assert job.inserted_count == 1


@pytest.mark.django_db
def test_canonical_name_upgrades_when_practitioner_listed_first(mocker, run_pipeline_inline):
    """If a practitioner listing is persisted before the clinic listing, the
    canonical row's name is upgraded to the clinic name on merge — the survivor
    never keeps a "Dr." name when a clinic name is available."""

    phone = '+15095559876'
    lat, lng = 41.5, -73.5
    pages = [(
        [
            _vet_place('vetA_pid', 'Dr. Brian Martz', phone=phone, lat=lat, lng=lng),
            _vet_place('clinicA_pid', 'Union Animal Hospital', phone=phone, lat=lat, lng=lng),
        ],
        None,
    )]
    client = FakeGooglePlacesClient(pages=pages)
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client,
    )

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    rows = Hospital.objects.filter(
        source=HospitalSource.GOOGLE_PLACES, phone_e164=phone, is_deleted=False,
    )
    assert rows.count() == 1
    survivor = rows.first()
    # The first-inserted row was the practitioner; the clinic merged into it
    # and upgraded the name.
    assert survivor.source_external_id == 'vetA_pid'
    assert survivor.name == 'Union Animal Hospital'
    assert survivor.metadata.get('member_place_ids') == ['clinicA_pid']
    assert job.merged_count == 1


@pytest.mark.django_db
def test_unknown_name_never_overwrites_practitioner_on_merge():
    """P3 — when an incoming listing's name resolves to the `'Unknown'`
    sentinel (Google omitted `displayName.text`, so `_upsert_hospital`
    substitutes `'Unknown'`), merging it into a canonical practitioner sibling
    MUST still absorb the place_id but MUST NOT upgrade the sibling's real name
    to the meaningless placeholder.

    This is exercised by calling `_upsert_hospital` directly: the full
    fetch→classify→persist pipeline can never deliver an `'Unknown'`-named
    place to the merge path because `rules.should_exclude` stamps an
    `excluded_reason='no_name'` on any place whose `displayName.text` is empty,
    and `_upsert_hospital` skips the merge for excluded listings. So the only
    place the sentinel reaches `_try_merge_into_sibling` is the persist step
    itself — which is what we drive here."""

    phone = '+15095557777'
    lat, lng = 39.0, -76.0

    # The earlier listing is canonical: a real practitioner name.
    canonical = Hospital.objects.create(
        source=HospitalSource.GOOGLE_PLACES,
        source_external_id='vetB_pid',
        name='Dr. Brian Martz',
        phone_e164=phone,
        latitude=lat,
        longitude=lng,
        metadata={},
    )

    # The incoming same-phone/same-coords listing carries NO displayName, so
    # `(raw.get('displayName') or {}).get('text')` is falsy and
    # `_upsert_hospital` derives `display_name == 'Unknown'`.
    item = {
        'place_id': 'noname_pid',
        'raw': {
            'id': 'noname_pid',
            'internationalPhoneNumber': phone,
            'location': {'latitude': lat, 'longitude': lng},
        },
    }

    with transaction.atomic():
        sourcing_tasks._upsert_hospital(item)

    # The merge still happened: persisted as a merge, not a fresh insert.
    assert item['_persist_outcome'] == 'merged'

    rows = Hospital.objects.filter(
        source=HospitalSource.GOOGLE_PLACES, phone_e164=phone, is_deleted=False,
    )
    assert rows.count() == 1
    survivor = rows.first()
    assert survivor.pk == canonical.pk
    # Name upgrade SUPPRESSED: the real practitioner name survives, NOT 'Unknown'.
    assert survivor.name == 'Dr. Brian Martz'
    # The place_id IS absorbed — only the name upgrade was suppressed.
    assert survivor.metadata.get('member_place_ids') == ['noname_pid']


@pytest.mark.django_db
def test_different_phones_stay_as_two_rows(mocker, run_pipeline_inline):
    """Two clinics with DIFFERENT phones are distinct practices — no merge,
    two live Hospital rows, `merged_count == 0`."""

    pages = [(
        [
            _vet_place('clinicX_pid', 'Sunset Pet Hospital', phone='+15095550001', lat=40.0, lng=-74.0),
            _vet_place('clinicY_pid', 'Riverside Animal Clinic', phone='+15095550002', lat=42.0, lng=-71.0),
        ],
        None,
    )]
    client = FakeGooglePlacesClient(pages=pages)
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client,
    )

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    assert Hospital.objects.filter(
        source=HospitalSource.GOOGLE_PLACES, is_deleted=False,
    ).count() == 2
    assert job.merged_count == 0
    assert job.inserted_count == 2


@pytest.mark.django_db
def test_toll_free_phone_never_merges(mocker, run_pipeline_inline):
    """Two listings sharing the SAME toll-free phone (+1800…) are NOT a
    practice identity — a toll-free line is a shared central booking number.
    No merge: 2 rows, `merged_count == 0`."""

    toll_free = '+18005551234'
    pages = [(
        [
            _vet_place('tf_clinic1_pid', 'Northside Pet Hospital',
                       phone=toll_free, lat=40.0, lng=-74.0),
            _vet_place('tf_clinic2_pid', 'Southside Animal Clinic',
                       phone=toll_free, lat=40.0, lng=-74.0),
        ],
        None,
    )]
    client = FakeGooglePlacesClient(pages=pages)
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client,
    )

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    assert Hospital.objects.filter(
        source=HospitalSource.GOOGLE_PLACES, is_deleted=False,
    ).count() == 2
    assert job.merged_count == 0
    assert job.inserted_count == 2


@pytest.mark.django_db
def test_missing_phone_never_merges(mocker, run_pipeline_inline):
    """A listing with NO phone has no practice identity to merge on. Two
    listings, one phone-less → no merge, 2 rows, `merged_count == 0`."""

    with_phone = _vet_place('phone_pid', 'Elm Street Pet Hospital',
                            phone='+15095557777', lat=40.0, lng=-74.0)
    no_phone = _vet_place('nophone_pid', 'Oak Street Animal Clinic',
                          phone='', lat=40.0, lng=-74.0)
    no_phone.pop('internationalPhoneNumber', None)

    pages = [([with_phone, no_phone], None)]
    client = FakeGooglePlacesClient(pages=pages)
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client,
    )

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    assert Hospital.objects.filter(
        source=HospitalSource.GOOGLE_PLACES, is_deleted=False,
    ).count() == 2
    assert job.merged_count == 0
    assert job.inserted_count == 2


@pytest.mark.django_db
def test_same_phone_far_apart_does_not_merge(mocker, run_pipeline_inline):
    """Same phone but coords >250m apart is a coincidental phone collision,
    not the same clinic — the proximity guard rejects the merge. 2 rows,
    `merged_count == 0`."""

    phone = '+15095553333'
    # ~1.1 km apart in latitude (0.01° ≈ 1113m) — well beyond the 250m radius.
    pages = [(
        [
            _vet_place('near_pid', 'Hilltop Pet Hospital',
                       phone=phone, lat=40.000, lng=-74.0),
            _vet_place('far_pid', 'Valley Animal Clinic',
                       phone=phone, lat=40.010, lng=-74.0),
        ],
        None,
    )]
    client = FakeGooglePlacesClient(pages=pages)
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client,
    )

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    assert Hospital.objects.filter(
        source=HospitalSource.GOOGLE_PLACES, is_deleted=False,
    ).count() == 2
    assert job.merged_count == 0
    assert job.inserted_count == 2


@pytest.mark.django_db
def test_live_clinic_not_absorbed_by_excluded_sibling(mocker, run_pipeline_inline):
    """H2 — a real operational clinic must never merge into a stale excluded
    listing sharing its phone. The non-operational listing is persisted first
    (lowest id) carrying `excluded_reason='not_operational'`; a later
    OPERATIONAL clinic with the same phone gets its OWN live keeper row, not
    absorbed and not carrying the exclusion (so it can enter the call queue)."""

    phone = '+15095554444'
    lat, lng = 40.0, -74.0
    closed = _vet_place('closed_pid', 'Old Vet Hospital (Closed)',
                        phone=phone, lat=lat, lng=lng)
    closed['businessStatus'] = 'CLOSED_PERMANENTLY'   # → excluded_reason set
    live = _vet_place('live_pid', 'New Animal Hospital',
                      phone=phone, lat=lat, lng=lng)

    pages = [([closed, live], None)]
    client = FakeGooglePlacesClient(pages=pages)
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client,
    )

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    # Two distinct rows: the excluded carcass and the live clinic.
    excluded_row = Hospital.objects.get(source_external_id='closed_pid')
    live_row = Hospital.objects.get(source_external_id='live_pid')
    assert excluded_row.excluded_reason == 'not_operational'
    # The live clinic is its own row — NOT merged into the excluded carcass —
    # and carries no exclusion, so it is callable.
    assert live_row.excluded_reason is None
    assert live_row.metadata.get('member_place_ids') in (None, [])
    assert job.merged_count == 0


@pytest.mark.django_db
def test_excluded_listing_not_absorbed_by_live_sibling(mocker, run_pipeline_inline):
    """Reverse of H2 — an OPERATIONAL clinic is persisted FIRST (lowest id),
    then a non-operational listing with the SAME phone arrives. The excluded
    listing must NOT merge into the live sibling: it becomes its OWN row
    carrying `excluded_reason`, the live row's `member_place_ids` stays clean,
    and the excluded place is not counted toward `merged_count`. Without the
    `and not excluded_reason` guard the closed listing would be absorbed into
    the live row and its exclusion never recorded."""

    phone = '+15095556666'
    lat, lng = 40.0, -74.0
    # Active listing FIRST so it is inserted as the canonical row; the bug path
    # only triggers when a live sibling already exists for the excluded place.
    live = _vet_place('live_first_pid', 'New Animal Hospital',
                      phone=phone, lat=lat, lng=lng)
    closed = _vet_place('closed_second_pid', 'Old Vet Hospital (Closed)',
                        phone=phone, lat=lat, lng=lng)
    closed['businessStatus'] = 'CLOSED_PERMANENTLY'   # → excluded_reason set

    pages = [([live, closed], None)]
    client = FakeGooglePlacesClient(pages=pages)
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client,
    )

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()

    # The excluded listing is its OWN persisted row carrying the exclusion —
    # never merged into the live sibling.
    excluded_row = Hospital.objects.get(source_external_id='closed_second_pid')
    live_row = Hospital.objects.get(source_external_id='live_first_pid')
    assert excluded_row.excluded_reason is not None
    assert excluded_row.excluded_reason == 'not_operational'
    # The live sibling never absorbed the closed place_id.
    assert 'closed_second_pid' not in (live_row.metadata.get('member_place_ids') or [])
    assert live_row.excluded_reason is None
    assert job.merged_count == 0


@pytest.mark.django_db
def test_label_locked_sibling_never_merged_into(mocker, run_pipeline_inline):
    """H1 — a `label_locked=True` row was hand-corrected by an operator. An
    incoming same-phone practitioner listing must NOT merge into it (which
    would mutate its name/contact). The locked row's name + contact stay
    exactly as the operator left them; the incoming place creates its own row."""

    phone = '+15095555555'
    lat, lng = 40.0, -74.0
    locked = Hospital.objects.create(
        source=HospitalSource.GOOGLE_PLACES,
        source_external_id='locked_pid',
        name='Operator Corrected Hospital',
        phone_e164=phone,
        website='https://operator-fixed.example',
        formatted_address='1 Operator Way',
        latitude=lat,
        longitude=lng,
        label_locked=True,
        metadata={},
    )

    pages = [(
        [_vet_place('incoming_vet_pid', 'Dr. Brian Martz',
                    phone=phone, lat=lat, lng=lng)],
        None,
    )]
    client = FakeGooglePlacesClient(pages=pages)
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client,
    )

    job = _make_job()
    run_pipeline_inline(job.pk)
    job.refresh_from_db()
    locked.refresh_from_db()

    # The locked row is untouched in name/contact — never a merge target.
    assert locked.name == 'Operator Corrected Hospital'
    assert locked.website == 'https://operator-fixed.example'
    assert locked.formatted_address == '1 Operator Way'
    assert (locked.metadata.get('member_place_ids') or []) == []
    # The incoming practitioner created its OWN row instead of merging.
    incoming = Hospital.objects.get(source_external_id='incoming_vet_pid')
    assert incoming.pk != locked.pk
    assert job.merged_count == 0


@pytest.mark.django_db
def test_merge_is_idempotent_across_reruns(mocker, run_pipeline_inline):
    """M1 — re-running the same place_ids must not re-count merges. First pass:
    clinic + 2 practitioners collapse to 1 row, `merged_count == 2`. Second
    pass over the SAME place_ids: `member_place_ids` is unchanged and
    `merged_count` does NOT grow (the place_ids are already absorbed)."""

    phone = '+15095556666'
    lat, lng = 40.0, -74.0

    def _build_pages():
        return [(
            [
                _vet_place('idem_clinic_pid', 'Lakeside Pet Hospital',
                           phone=phone, lat=lat, lng=lng),
                _vet_place('idem_vet1_pid', 'Dr. Brian Martz',
                           phone=phone, lat=lat, lng=lng),
                _vet_place('idem_vet2_pid', 'Halligan Lori DVM',
                           phone=phone, lat=lat, lng=lng),
            ],
            None,
        )]

    # First pass.
    client1 = FakeGooglePlacesClient(pages=_build_pages())
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client1,
    )
    job1 = _make_job()
    run_pipeline_inline(job1.pk)
    job1.refresh_from_db()

    survivor = Hospital.objects.get(source_external_id='idem_clinic_pid')
    first_members = set(survivor.metadata.get('member_place_ids') or [])
    assert first_members == {'idem_vet1_pid', 'idem_vet2_pid'}
    assert job1.merged_count == 2

    # Second pass over the same place_ids — a fresh job, equivalent script.
    client2 = FakeGooglePlacesClient(pages=_build_pages())
    mocker.patch(
        'services.external.google_places.client.get_client', return_value=client2,
    )
    job2 = _make_job()
    run_pipeline_inline(job2.pk)
    job2.refresh_from_db()

    survivor.refresh_from_db()
    # member_place_ids unchanged — no place_id re-added.
    assert set(survivor.metadata.get('member_place_ids') or []) == first_members
    # Still exactly one live row for the phone.
    assert Hospital.objects.filter(
        source=HospitalSource.GOOGLE_PLACES, phone_e164=phone, is_deleted=False,
    ).count() == 1
    # The second pass counted ZERO fresh merges (re-run no-op, M1).
    assert job2.merged_count == 0
