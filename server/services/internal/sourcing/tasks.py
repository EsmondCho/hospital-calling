"""Celery task pipeline for the hospital sourcing tile fan-out (DRT-5265).

Why recursive tiling (instead of one query per city)?
    Google Places `searchText` returns at most 60 results for any single
    query — 20 per page, and only up to 3 pages via `nextPageToken`
    (`SOURCING_MAX_PAGES`). Past 60, the API simply stops paginating; it
    never signals "there were more", so a dense metro (hundreds of vet
    clinics) would be silently truncated and we'd miss most of the market.
    There is no radius/limit knob that lifts the 60 cap.

    So we can't trust any query that comes back near the cap: a tile whose
    cumulative result count crosses `SOURCING_SPLIT_THRESHOLD` (55, just
    under 60) is *assumed truncated*. Rather than accept the partial list,
    we quarter that tile's rectangle into 4 smaller tiles and re-run the
    same search on each — recursively — until every leaf tile returns
    comfortably under the cap (so we know it's complete) or we hit a
    guardrail (`max_depth` / `SOURCING_MIN_TILE_METERS`), which is recorded
    as a `capped_at_min_size` potential miss. Shrinking the area is the only
    lever that reduces results-per-query below the cap, so geographic
    subdivision is what gives us exhaustive coverage. `call_limit` bounds the
    total Google calls (≈ cost) so a pathological split can't run away.

Topology (per SourcingJob):

    start_job(job_id)
      → PENDING→RUNNING, started_at set
      → resolve_viewport(job_id)                       # queue: sourcing_search
         → resolve_city_viewport(city, state) → root tile (depth=0)
         → fetch_tile(job_id, root.id)

    fetch_tile(job_id, tile_id)                        # queue: sourcing_search
      → searchText for the tile rectangle (one page)
      → classify_batch(job_id, tile_id, places)        # queue: celery (LLM)
         → persist_batch(job_id, tile_id, classified)  # queue: celery
            ↳ nextPageToken + page_count < MAX_PAGES → fetch_tile (same tile)
            ↳ cap suspected + can split → split into 4 children, group fan-out
            ↳ cap suspected + min-size/depth limit → COMPLETED + capped flag
            ↳ otherwise → COMPLETED
            → try_finalize(job_id)

    try_finalize(job_id)
      → no PENDING/RUNNING tiles left → finalize_job (idempotent)

Each task is `acks_late=True` and re-checks `SourcingJob.status` on entry,
so a replay or a CANCELLED job bails cleanly. Tile failures are isolated:
a Google call failure — or an unhandled classify/persist-stage crash —
marks only that `SourcingTile`, never the job.
"""

from __future__ import annotations

import re

import structlog
from celery import group, shared_task
from django.conf import settings
from django.db import connection, transaction
from django.db.models import F, Q
from django.db.models.functions import Now
from django.utils import timezone

from hospital.models import Hospital
from hospital.vars import HospitalAppointmentMode, HospitalOwnership, HospitalSource
from sourcing.models import SourcingJob, SourcingTile
from sourcing.vars import (
    TERMINAL_STATUSES,
    UNRESOLVED_TILE_STATUSES,
    PartialReason,
    SourcingJobStatus,
    SourcingTileStatus,
)
from utils.geo import haversine_meters, split_quadrants, tile_edge_meters

logger = structlog.get_logger(__name__)


# Normalized error codes stored on SourcingTile.error_message /
# SourcingJob.error_message. The verbose upstream detail goes to `logger`
# only — never the raw Google response text into a DB column.
_ERROR_RATE_LIMITED = 'rate_limited'
_ERROR_UPSTREAM = 'upstream_error'
_ERROR_CITY_NOT_FOUND = 'city_not_found'
_ERROR_PIPELINE = 'pipeline_error'   # unhandled classify/persist-stage crash


# Practice-dedup (DRT-5297). Google `searchText` returns one "place" per
# veterinarian at a practice — the clinic listing PLUS a separate listing for
# each DVM, each with its own `place_id`. Deduping on `place_id` alone made
# every practitioner row a fresh Hospital, inflating counts and causing the
# call campaign to dial the same clinic many times. At persist time we treat a
# *practice identity* as `normalized phone (+ geo proximity)` and merge a
# brand-new place_id into the existing live row that shares it.
_MERGE_RADIUS_M = 250.0

# North-American toll-free area codes. A toll-free number is shared across
# unrelated locations (a chain's central booking line, an answering service),
# so it is NOT a reliable practice identity and must never drive a phone-merge.
_TOLL_FREE_AREA_CODES = frozenset({'800', '888', '877', '866', '855', '844', '833', '822'})

# An individual practitioner's listing name — "Dr. Brian Martz", "Halligan
# Lori DVM", "... Nestor Derek D DVM". When a clinic and its DVM listings
# merge, we prefer the clinic name and treat a practitioner name as
# upgradeable. Case-insensitive; covers a leading "Dr.", a trailing "DVM"
# (with or without dots / a leading comma).
_PRACTITIONER_NAME_REGEX = re.compile(
    r'\bDVM\b|\bD\.?V\.?M\.?\b|^Dr\.?\s|,\s*DVM',
    re.IGNORECASE,
)

# A clinic-type keyword anywhere in the name means it's a clinic listing, not a
# per-vet listing — even when it leads with "Dr." ("Dr. Marc's Animal Clinic").
# This pre-check guards the canonical-name upgrade from clobbering a good clinic
# name (P2-1).
_CLINIC_TYPE_REGEX = re.compile(
    r'animal\s+(hospital|clinic)|vet(erinary)?\s+(clinic|center|hospital|care|practice)|pet\s+(hospital|clinic|care)',
    re.IGNORECASE,
)


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────


def _is_toll_free(e164: str | None) -> bool:
    """True for a North-American toll-free number (`+1` + a toll-free NPA).

    Toll-free lines are shared across unrelated locations, so they can't
    identify a single practice — the practice-dedup phone-merge skips them.
    """

    if not e164 or not e164.startswith('+1') or len(e164) < 5:
        return False
    return e164[2:5] in _TOLL_FREE_AREA_CODES


def _is_practitioner_name(name: str | None) -> bool:
    """True when `name` looks like an individual veterinarian's listing.

    Used by the practice-dedup canonical-name upgrade: a sibling carrying a
    practitioner name is replaced by the incoming clinic name on merge.
    """

    if not name:
        return False
    if _CLINIC_TYPE_REGEX.search(name):
        return False
    return _PRACTITIONER_NAME_REGEX.search(name) is not None


def _find_practice_sibling(
    *,
    phone_e164: str,
    latitude: float | None,
    longitude: float | None,
    exclude_place_id: str,
) -> Hospital | None:
    """Find an existing live Google-Places hospital that shares this practice.

    A *practice* is identified by its normalized phone; the lowest `id`
    (earliest-inserted) wins as the canonical row so concurrent workers all
    converge on the same survivor. Proximity guard: if BOTH the candidate row
    and the incoming place carry coordinates, the two must be within
    `_MERGE_RADIUS_M` meters — this rejects a coincidental phone collision
    between two far-apart clinics. If either side lacks coordinates we accept
    the phone match (no basis to reject).

    Two kinds of row are disqualified as merge targets:
      * `label_locked=True` (H1) — an operator hand-corrected this row. Merging
        would mutate its name/contact/metadata, breaking the operator-correction
        contract (the locked-row path only ever refreshes contact, never
        classification/name). A brand-new place_id then just creates its own row.
      * a row carrying an `excluded_reason` (H2) — a stale/non-operational
        listing. Merging a genuine operational clinic into it would inherit the
        exclusion and keep the clinic out of the call queue (which gates on
        INDEPENDENT and no `excluded_reason`). `excluded_reason` is nullable, so
        the keeper set is "null OR empty string".
    """

    candidates = (
        Hospital.objects
        .filter(
            source=HospitalSource.GOOGLE_PLACES,
            phone_e164=phone_e164,
            is_deleted=False,
            label_locked=False,
        )
        .filter(Q(excluded_reason__isnull=True) | Q(excluded_reason=''))
        .exclude(source_external_id=exclude_place_id)
        .order_by('id')
    )
    for candidate in candidates:
        if (
            latitude is not None and longitude is not None
            and candidate.latitude is not None and candidate.longitude is not None
        ):
            distance = haversine_meters(
                lat1=float(latitude), lng1=float(longitude),
                lat2=float(candidate.latitude), lng2=float(candidate.longitude),
            )
            if distance > _MERGE_RADIUS_M:
                continue
        return candidate
    return None


def _try_merge_into_sibling(
    *,
    place_id: str,
    name: str,
    phone_e164: str,
    website: str | None,
    formatted_address: str | None,
    latitude: float | None,
    longitude: float | None,
) -> str | None:
    """Merge a brand-new place_id into its existing practice row if one exists.

    Returns the persist outcome the caller should stamp and short-circuit on:
      * `'merged'` — the place_id was newly absorbed into the canonical row;
        counts toward `merged_count`.
      * `'merged_noop'` — the place_id is ALREADY a member of the sibling (a
        re-run of the same listing). No counter bump, no field rewrite — the
        caller still skips the create path but it is NOT counted as `merged`
        (M1: avoids inflating `merged_count` + a needless write on every run).
    Returns None when there is no sibling and the place should fall through to
    the normal get_or_create.

    Race-safety: `persist_batch` runs concurrently (a split city fans out to a
    celery `group`), so two workers can each hold a brand-new place_id for the
    same practice. Without serialization both would read "no sibling yet" and
    both would create a row — re-introducing the duplicate this whole change
    removes. A transaction-level advisory lock keyed on the normalized phone
    forces same-phone inserts to run one at a time; it auto-releases at
    commit/rollback (we are already inside `transaction.atomic()`). Inside the
    lock we re-check by place_id (a concurrent worker may have just inserted
    this very place_id) before looking for a sibling.
    """

    # `pg_advisory_xact_lock` is transaction-scoped: outside a transaction
    # (autocommit) it releases immediately and the race guard is void. Enforce
    # the invariant explicitly — an exception, not `assert` (which `-O` strips).
    if not connection.in_atomic_block:
        raise RuntimeError('_try_merge_into_sibling must run inside transaction.atomic()')

    with connection.cursor() as cur:
        cur.execute(
            'SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', [phone_e164],
        )

    # Re-check under the lock: a concurrent worker may have inserted this exact
    # place_id between our pre-lock check and acquiring the lock. If so, this is
    # no longer a brand-new place_id — fall through to the normal update path.
    if (
        Hospital.objects
        .filter(source=HospitalSource.GOOGLE_PLACES, source_external_id=place_id)
        .exists()
    ):
        return None

    sibling = _find_practice_sibling(
        phone_e164=phone_e164,
        latitude=latitude,
        longitude=longitude,
        exclude_place_id=place_id,
    )
    if sibling is None:
        return None

    metadata = dict(sibling.metadata or {})
    member_place_ids = list(metadata.get('member_place_ids') or [])
    # Re-run idempotency (M1): this exact place_id is already absorbed into the
    # sibling. Don't re-count it as a fresh merge and don't rewrite any fields
    # — just short-circuit the create path as a no-op.
    if place_id in member_place_ids:
        return 'merged_noop'
    member_place_ids.append(place_id)
    metadata['member_place_ids'] = member_place_ids
    metadata['google_places_fetched_at'] = timezone.now().isoformat()

    updates: dict = {'metadata': metadata}

    # Canonical-name upgrade: a clinic listing should win over a per-vet
    # listing. Only upgrade when the sibling currently holds a practitioner
    # name AND the incoming name does not — never clobber a good clinic name.
    # Guard the `'Unknown'` sentinel (`_upsert_hospital` substitutes it when
    # Google omits `displayName.text`): it is not a practitioner name, so the
    # condition would otherwise overwrite a sibling's real name with the
    # placeholder.
    if (
        name != 'Unknown'
        and _is_practitioner_name(sibling.name)
        and not _is_practitioner_name(name)
    ):
        updates['name'] = name

    # Backfill contact / address only where the sibling is currently empty —
    # the canonical row's existing good data is never overwritten on merge.
    if not sibling.website and website:
        updates['website'] = website
    if not sibling.formatted_address and formatted_address:
        updates['formatted_address'] = formatted_address
    if sibling.latitude is None and latitude is not None:
        updates['latitude'] = latitude
    if sibling.longitude is None and longitude is not None:
        updates['longitude'] = longitude

    rows = Hospital.objects.filter(pk=sibling.pk).update(updated_at=Now(), **updates)
    if rows == 0:
        # Sibling vanished between read and write — fall through to the normal
        # get_or_create path so the place_id is never orphaned (P4-6).
        return None
    logger.info(
        'sourcing.persist_batch.practice_merged',
        sibling_id=sibling.pk, place_id=place_id, phone_e164=phone_e164,
    )
    return 'merged'

def _job_running(job_id: int) -> SourcingJob | None:
    """Return the job if it's safe to keep running; None if we should bail."""

    try:
        job = SourcingJob.objects.get(pk=job_id)
    except SourcingJob.DoesNotExist:
        logger.info('sourcing.task.job_missing', job_id=job_id)
        return None
    if job.status in TERMINAL_STATUSES:
        logger.info('sourcing.task.job_terminal', job_id=job_id, status=job.status)
        return None
    return job


def _tile_viewport(tile: SourcingTile) -> dict[str, float]:
    """SourcingTile Decimal bounds → float bbox for the Google client / geo utils."""

    return {
        'south': float(tile.south),
        'west': float(tile.west),
        'north': float(tile.north),
        'east': float(tile.east),
    }


# ──────────────────────────────────────────────────────────────────────────
# Tasks
# ──────────────────────────────────────────────────────────────────────────

@shared_task(name='sourcing.start_job', acks_late=True)
def start_job(*, job_id: int) -> dict:
    """Entry point. Transition PENDING→RUNNING and hand off to `resolve_viewport`."""

    job = _job_running(job_id)
    if job is None:
        return {'result': 'skipped'}

    updated = (
        SourcingJob.objects
        .filter(pk=job_id, status=SourcingJobStatus.PENDING)
        .update(status=SourcingJobStatus.RUNNING, started_at=timezone.now())
    )
    if not updated:
        # ACKS_LATE replay or operator-cancelled between our check and now.
        return {'result': 'not_pending'}

    resolve_viewport.apply_async(kwargs={'job_id': job_id})
    return {'result': 'started'}


@shared_task(name='sourcing.resolve_viewport', acks_late=True)
def resolve_viewport(*, job_id: int) -> dict:
    """Resolve the city viewport and create the root tile.

    A viewport-resolution failure is a root-level fatal error — the job
    goes FAILED (unlike per-tile failures, which are isolated).
    """

    job = _job_running(job_id)
    if job is None or job.status != SourcingJobStatus.RUNNING:
        return {'result': 'skipped'}

    from services.external.google_places.client import get_client

    try:
        viewport = get_client().resolve_city_viewport(
            city=job.city or '', state_code=job.state_code,
        )
    except Exception as e:
        logger.exception('sourcing.resolve_viewport.error', job_id=job_id)
        SourcingJob.objects.filter(pk=job_id).update(
            status=SourcingJobStatus.FAILED,
            error_message=_ERROR_UPSTREAM,
            error_count=F('error_count') + 1,
            completed_at=timezone.now(),
        )
        return {'result': 'resolve_error'}

    if viewport is None:
        logger.warning(
            'sourcing.resolve_viewport.city_not_found',
            job_id=job_id, city=job.city, state_code=job.state_code,
        )
        SourcingJob.objects.filter(pk=job_id).update(
            status=SourcingJobStatus.FAILED,
            error_message=_ERROR_CITY_NOT_FOUND,
            error_count=F('error_count') + 1,
            completed_at=timezone.now(),
        )
        return {'result': 'city_not_found'}

    with transaction.atomic():
        SourcingJob.objects.filter(pk=job_id).update(
            root_south=viewport['south'],
            root_west=viewport['west'],
            root_north=viewport['north'],
            root_east=viewport['east'],
            total_tiles=F('total_tiles') + 1,
        )
        root = SourcingTile.objects.create(
            job_id=job_id,
            parent=None,
            south=viewport['south'],
            west=viewport['west'],
            north=viewport['north'],
            east=viewport['east'],
            depth=0,
            status=SourcingTileStatus.PENDING,
        )

    fetch_tile.apply_async(kwargs={'job_id': job_id, 'tile_id': root.id})
    return {'result': 'resolved', 'root_tile_id': root.id}


@shared_task(name='sourcing.fetch_tile', acks_late=True)
def fetch_tile(*, job_id: int, tile_id: int, is_retry: bool = False) -> dict:
    """Search one tile rectangle (one page) and hand off to `classify_batch`.

    `is_retry` is set only when `_handle_tile_error` re-enqueues a tile after
    a rate-limit failure. A retry reuses the call-budget slot the original
    attempt already reserved, so it must not reserve a second one.
    """

    job = _job_running(job_id)
    if job is None or job.status != SourcingJobStatus.RUNNING:
        return {'result': 'skipped'}

    try:
        tile = SourcingTile.objects.get(pk=tile_id, job_id=job_id)
    except SourcingTile.DoesNotExist:
        logger.info('sourcing.fetch_tile.tile_missing', job_id=job_id, tile_id=tile_id)
        return {'result': 'tile_missing'}

    # Idempotent narrow: PENDING → RUNNING only. A redelivered task whose
    # tile is already RUNNING (or resolved) bails here — `acks_late` can
    # double-deliver, and a fresh fetch of a RUNNING tile would duplicate
    # the Google call. `_handle_tile_error` flips a retry back to PENDING,
    # so the retry path stays consistent with this narrow.
    narrowed = (
        SourcingTile.objects
        .filter(pk=tile_id, status=SourcingTileStatus.PENDING)
        .update(status=SourcingTileStatus.RUNNING)
    )
    if not narrowed:
        return {'result': 'tile_not_pending'}

    from services.external.google_places.client import GooglePlacesError, get_client

    # Per-job call-budget guard. A retry already holds a reserved slot, so it
    # skips reservation; a fresh fetch (initial or pagination) reserves one
    # atomically via compare-and-increment so concurrent tiles can never
    # overshoot `call_limit` (P1-2a).
    if not is_retry:
        reserved = (
            SourcingJob.objects
            .filter(pk=job_id, call_count__lt=F('call_limit'))
            .update(call_count=F('call_count') + 1)
        )
        if not reserved:
            # Budget exhausted — close this tile, mark the job partial.
            _finalize_call_limit(job_id=job_id, tile_id=tile_id)
            return {'result': 'call_limit'}

    try:
        places, next_page_token, cost = get_client().search_vet_hospitals(
            viewport=_tile_viewport(tile),
            page_token=tile.page_cursor,
        )
    except GooglePlacesError as e:
        return _handle_tile_error(job_id=job_id, tile_id=tile_id, error=e)
    except Exception as e:  # noqa: BLE001 — any transport error isolates to the tile
        return _handle_tile_error(job_id=job_id, tile_id=tile_id, error=e)

    SourcingJob.objects.filter(pk=job_id).update(
        fetched_count=F('fetched_count') + len(places),
        actual_cost_usd=F('actual_cost_usd') + cost,
    )
    SourcingTile.objects.filter(pk=tile_id).update(
        fetched_count=F('fetched_count') + len(places),
        page_count=F('page_count') + 1,
        cost_usd=F('cost_usd') + cost,
        page_cursor=next_page_token,
    )

    classify_batch.apply_async(kwargs={
        'job_id': job_id,
        'tile_id': tile_id,
        'places_payload': places,
        'has_next_page': bool(next_page_token),
    })
    return {'result': 'fetched', 'count': len(places), 'has_next_page': bool(next_page_token)}


def _finalize_call_limit(*, job_id: int, tile_id: int) -> None:
    """Close a tile that hit the per-job call budget and mark the job partial.

    The [tile COMPLETED + job counter increments] run in one transaction so
    `finalize_job` can't read a stale counter; `try_finalize` is enqueued on
    commit so it observes the committed `completed_tiles` / `partial` state
    (P1-1).
    """

    with transaction.atomic():
        SourcingTile.objects.filter(pk=tile_id).update(status=SourcingTileStatus.COMPLETED)
        SourcingJob.objects.filter(pk=job_id).update(
            completed_tiles=F('completed_tiles') + 1,
            partial=True,
            partial_reason=PartialReason.CALL_LIMIT,
        )
        transaction.on_commit(
            lambda: try_finalize.apply_async(kwargs={'job_id': job_id}),
        )
    logger.info('sourcing.fetch_tile.call_limit_reached', job_id=job_id, tile_id=tile_id)


def _is_rate_limited(error: Exception) -> bool:
    """True for a Google rate-limit failure.

    Google Places New v1 returns HTTP 429 (`RESOURCE_EXHAUSTED`) when the
    request quota is exceeded. As a belt-and-suspenders check we also accept
    a non-429 response whose error body carries `RESOURCE_EXHAUSTED` in
    `error.status` — `GooglePlacesError` keeps the raw body in `details`.
    """

    if getattr(error, 'status_code', None) == 429:
        return True
    details = getattr(error, 'details', None)
    if isinstance(details, dict):
        status = (details.get('error') or {}).get('status')
        if status == 'RESOURCE_EXHAUSTED':
            return True
    return False


def _handle_tile_error(*, job_id: int, tile_id: int, error: Exception) -> dict:
    """Isolate a tile-level Google failure — never touches `SourcingJob.status`.

    A rate-limit failure (HTTP 429 / `RESOURCE_EXHAUSTED`) is retried with
    exponential backoff while `retry_count` is below the cap; other errors
    (or an exhausted retry budget) mark the tile FAILED.
    """

    status_code = getattr(error, 'status_code', None)
    tile = SourcingTile.objects.filter(pk=tile_id).first()
    if tile is None:
        return {'result': 'tile_missing'}

    is_rate_limited = _is_rate_limited(error)
    if is_rate_limited and tile.retry_count < settings.SOURCING_TILE_MAX_RETRIES:
        SourcingTile.objects.filter(pk=tile_id).update(
            status=SourcingTileStatus.PENDING,
            retry_count=F('retry_count') + 1,
        )
        countdown = 2 ** tile.retry_count
        logger.info(
            'sourcing.fetch_tile.rate_limited_retry',
            job_id=job_id, tile_id=tile_id, retry_count=tile.retry_count + 1,
            countdown=countdown,
        )
        # `is_retry=True`: the original attempt already reserved a call slot;
        # the retry reuses it instead of reserving another (P1-2a).
        fetch_tile.apply_async(
            kwargs={'job_id': job_id, 'tile_id': tile_id, 'is_retry': True},
            countdown=countdown,
        )
        return {'result': 'rate_limited_retry'}

    # Store only a normalized code in `error_message`; the verbose upstream
    # detail goes to `logger` (P2 — error-message normalization).
    error_code = _ERROR_RATE_LIMITED if is_rate_limited else _ERROR_UPSTREAM
    logger.warning(
        'sourcing.fetch_tile.failed',
        job_id=job_id, tile_id=tile_id, status_code=status_code,
        error_code=error_code, error=str(error),
    )
    # [tile FAILED + job counter increments] in one transaction so a racing
    # `try_finalize` can't partial-misjudge on a stale counter; enqueue
    # `try_finalize` on commit (P1-1).
    with transaction.atomic():
        SourcingTile.objects.filter(pk=tile_id).update(
            status=SourcingTileStatus.FAILED,
            error_message=error_code,
        )
        SourcingJob.objects.filter(pk=job_id).update(
            failed_tile_count=F('failed_tile_count') + 1,
            completed_tiles=F('completed_tiles') + 1,
            error_count=F('error_count') + 1,
        )
        transaction.on_commit(
            lambda: try_finalize.apply_async(kwargs={'job_id': job_id}),
        )
    return {'result': 'tile_failed'}


def _fail_tile(*, job_id: int, tile_id: int, error: Exception) -> dict:
    """Fail a tile after an unhandled classify/persist-stage crash.

    The classify → persist leg has no equivalent of `_handle_tile_error`'s
    Google-failure isolation: an exception there used to leave the tile —
    and so the whole job — stuck in RUNNING forever. Marking the tile
    FAILED lets `try_finalize` close the job out as partial
    (`tile_failures`), exactly as a failed Google call already does.

    Only an unresolved tile is flipped, so an `acks_late` replay (or a
    crash after `_advance_tile` already resolved the tile) can't
    double-count `failed_tile_count`. Called from inside an `except`
    block, so `logger.exception` captures the traceback.
    """

    logger.exception(
        'sourcing.tile.stage_crashed',
        job_id=job_id, tile_id=tile_id, error_code=_ERROR_PIPELINE,
        error=str(error),
    )
    with transaction.atomic():
        flipped = (
            SourcingTile.objects
            .filter(pk=tile_id, status__in=UNRESOLVED_TILE_STATUSES)
            .update(status=SourcingTileStatus.FAILED, error_message=_ERROR_PIPELINE)
        )
        if flipped:
            SourcingJob.objects.filter(pk=job_id).update(
                failed_tile_count=F('failed_tile_count') + 1,
                completed_tiles=F('completed_tiles') + 1,
                error_count=F('error_count') + 1,
            )
        transaction.on_commit(
            lambda: try_finalize.apply_async(kwargs={'job_id': job_id}),
        )
    return {'result': 'tile_failed'}


@shared_task(name='sourcing.classify_batch', acks_late=True)
def classify_batch(
    *, job_id: int, tile_id: int, places_payload: list[dict], has_next_page: bool,
) -> dict:
    """Classify a fetched page. An unhandled crash fails the tile via
    `_fail_tile` so the job can finalize instead of hanging in RUNNING."""

    job = _job_running(job_id)
    if job is None or job.status != SourcingJobStatus.RUNNING:
        return {'result': 'skipped'}
    try:
        return _run_classify_batch(
            job_id=job_id, tile_id=tile_id,
            places_payload=places_payload, has_next_page=has_next_page,
        )
    except Exception as e:  # noqa: BLE001 — a classify crash fails the tile, never hangs it
        return _fail_tile(job_id=job_id, tile_id=tile_id, error=e)


def _run_classify_batch(
    *, job_id: int, tile_id: int, places_payload: list[dict], has_next_page: bool,
) -> dict:
    """Body of `classify_batch` — wrapped so an exception fails the tile."""

    from services.internal.sourcing.classifier import HospitalClassifier
    from services.internal.sourcing.rules import match_chain, should_exclude

    classifier = HospitalClassifier()
    classified: list[dict] = []
    excluded = 0
    needs_review_local = 0
    input_tokens_total = 0
    output_tokens_total = 0

    for raw in places_payload:
        exclusion = should_exclude(raw)
        if exclusion.reason is not None:
            excluded += 1
            classified.append({
                'place_id': raw.get('id'),
                'raw': raw,
                'excluded_reason': exclusion.reason,
            })
            continue

        name = ((raw.get('displayName') or {}).get('text')) or ''
        rule_label = match_chain(name)
        llm_label = classifier.classify(raw, rule_label)

        if llm_label.needs_review:
            needs_review_local += 1
        input_tokens_total += llm_label.input_tokens
        output_tokens_total += llm_label.output_tokens

        classified.append({
            'place_id': raw.get('id'),
            'raw': raw,
            'rule_label': {
                'ownership': str(rule_label.ownership),
                'service_tags': [str(t) for t in rule_label.service_tags],
                'chain_brand_normalized': rule_label.chain_brand_normalized,
                'matched': rule_label.matched,
            },
            'llm_label': {
                'ownership': str(llm_label.ownership),
                'service_tags': [str(t) for t in llm_label.service_tags],
                'specialty_areas': list(llm_label.specialty_areas),
                'appointment_mode': str(llm_label.appointment_mode),
                'chain_brand_normalized': llm_label.chain_brand_normalized,
                'reasoning': llm_label.reasoning,
                'needs_review': llm_label.needs_review,
            },
            'suggested_ownership': (
                str(exclusion.suggested_ownership) if exclusion.suggested_ownership else None
            ),
        })

    SourcingJob.objects.filter(pk=job_id).update(
        excluded_count=F('excluded_count') + excluded,
        needs_review_count=F('needs_review_count') + needs_review_local,
        llm_input_tokens=F('llm_input_tokens') + input_tokens_total,
        llm_output_tokens=F('llm_output_tokens') + output_tokens_total,
    )

    persist_batch.apply_async(kwargs={
        'job_id': job_id,
        'tile_id': tile_id,
        'classified_payload': classified,
        'has_next_page': has_next_page,
    })
    return {'result': 'classified', 'count': len(places_payload), 'excluded': excluded}


@shared_task(name='sourcing.persist_batch', acks_late=True)
def persist_batch(
    *, job_id: int, tile_id: int, classified_payload: list[dict], has_next_page: bool,
) -> dict:
    """Persist a classified page. An unhandled crash fails the tile via
    `_fail_tile` so the job can finalize instead of hanging in RUNNING."""

    job = _job_running(job_id)
    if job is None or job.status != SourcingJobStatus.RUNNING:
        return {'result': 'skipped'}
    try:
        return _run_persist_batch(
            job_id=job_id, tile_id=tile_id,
            classified_payload=classified_payload, has_next_page=has_next_page,
        )
    except Exception as e:  # noqa: BLE001 — a persist crash fails the tile, never hangs it
        return _fail_tile(job_id=job_id, tile_id=tile_id, error=e)


def _run_persist_batch(
    *, job_id: int, tile_id: int, classified_payload: list[dict], has_next_page: bool,
) -> dict:
    """Body of `persist_batch` — wrapped so an exception fails the tile."""

    inserted = 0
    updated = 0
    skipped_locked = 0
    merged = 0
    error_local = 0

    for item in classified_payload:
        place_id = item.get('place_id')
        if not place_id:
            error_local += 1
            continue
        try:
            with transaction.atomic():
                _upsert_hospital(item)
        except Exception:
            logger.exception('sourcing.persist_batch.row_error',
                             job_id=job_id, place_id=place_id)
            error_local += 1
            continue

        outcome = item.get('_persist_outcome')
        if outcome == 'inserted':
            inserted += 1
        elif outcome == 'updated':
            updated += 1
        elif outcome == 'skipped_locked':
            skipped_locked += 1
        elif outcome == 'merged':
            merged += 1
        elif outcome == 'merged_noop':
            pass  # re-run no-op, intentionally uncounted

    SourcingJob.objects.filter(pk=job_id).update(
        inserted_count=F('inserted_count') + inserted,
        updated_count=F('updated_count') + updated,
        skipped_count=F('skipped_count') + skipped_locked,
        merged_count=F('merged_count') + merged,
        error_count=F('error_count') + error_local,
    )

    _advance_tile(job_id=job_id, tile_id=tile_id, has_next_page=has_next_page)

    return {
        'result': 'persisted',
        'inserted': inserted, 'updated': updated, 'skipped_locked': skipped_locked,
        'merged': merged,
    }


def _advance_tile(*, job_id: int, tile_id: int, has_next_page: bool) -> None:
    """Decide a tile's next move after a page persisted: paginate, split, or close.

    Re-reads the tile so the decision uses cumulative `fetched_count` /
    `page_count` (research §Q2 / §Q6).
    """

    tile = SourcingTile.objects.filter(pk=tile_id, job_id=job_id).first()
    if tile is None or tile.status != SourcingTileStatus.RUNNING:
        # Replay / cancellation between persist and here — nothing to do.
        return

    # More pages available — keep paginating the same tile. `countdown=3`
    # respects Google's 2-5s nextPageToken delay.
    if has_next_page and tile.page_count < settings.SOURCING_MAX_PAGES:
        # Reset to PENDING so the next `fetch_tile` clears its PENDING-only
        # entry guard — the tile is RUNNING here. Mirrors the retry path in
        # `_handle_tile_error`.
        SourcingTile.objects.filter(pk=tile_id).update(
            status=SourcingTileStatus.PENDING,
        )
        fetch_tile.apply_async(
            kwargs={'job_id': job_id, 'tile_id': tile_id}, countdown=3,
        )
        return

    cap_suspected = tile.fetched_count >= settings.SOURCING_SPLIT_THRESHOLD
    if cap_suspected:
        job = SourcingJob.objects.filter(pk=job_id).only('max_depth').first()
        max_depth = job.max_depth if job is not None else settings.SOURCING_MAX_DEPTH
        edge_meters = tile_edge_meters(**_tile_viewport(tile))
        can_split = (
            tile.depth < max_depth
            and edge_meters > settings.SOURCING_MIN_TILE_METERS
        )
        if can_split:
            _split_tile(job_id=job_id, tile=tile)
            return

        # Cap suspected but we've hit a guardrail — close the tile and
        # record the potential miss. [tile transition + job counters] in one
        # transaction; `try_finalize` enqueued on commit so it reads the
        # committed counters (P1-1).
        with transaction.atomic():
            SourcingTile.objects.filter(pk=tile_id).update(
                status=SourcingTileStatus.COMPLETED,
                capped_at_min_size=True,
            )
            SourcingJob.objects.filter(pk=job_id).update(
                completed_tiles=F('completed_tiles') + 1,
                capped_tile_count=F('capped_tile_count') + 1,
            )
            transaction.on_commit(
                lambda: try_finalize.apply_async(kwargs={'job_id': job_id}),
            )
        logger.info(
            'sourcing.tile.capped_at_min_size',
            job_id=job_id, tile_id=tile_id, depth=tile.depth, edge_meters=edge_meters,
        )
        return

    # Genuine end — fewer than the split threshold, no more pages. [tile
    # transition + job counter] in one transaction; `try_finalize` enqueued
    # on commit (P1-1).
    with transaction.atomic():
        SourcingTile.objects.filter(pk=tile_id).update(status=SourcingTileStatus.COMPLETED)
        SourcingJob.objects.filter(pk=job_id).update(
            completed_tiles=F('completed_tiles') + 1,
        )
        transaction.on_commit(
            lambda: try_finalize.apply_async(kwargs={'job_id': job_id}),
        )


def _split_tile(*, job_id: int, tile: SourcingTile) -> None:
    """Quarter a capped tile into 4 children and fan out `fetch_tile`.

    The [parent SPLIT + 4 child INSERT + counter increments] run in one
    `transaction.atomic()` so `try_finalize` never sees a window where the
    parent is resolved but the children don't exist yet (research §Q6).
    The child fan-out is scheduled via `transaction.on_commit` so the child
    rows are committed before any `fetch_tile` is enqueued (P2).

    `completed_tiles` is incremented for the parent: a SPLIT tile is resolved
    (its work is delegated to the children) and must count toward the
    `completed_tiles / total_tiles` progress ratio (P2 — progress bug).
    """

    with transaction.atomic():
        SourcingTile.objects.filter(pk=tile.pk).update(status=SourcingTileStatus.SPLIT)
        quadrants = split_quadrants(**_tile_viewport(tile))
        children = SourcingTile.objects.bulk_create([
            SourcingTile(
                job_id=job_id,
                parent_id=tile.pk,
                south=quadrant['south'],
                west=quadrant['west'],
                north=quadrant['north'],
                east=quadrant['east'],
                depth=tile.depth + 1,
                status=SourcingTileStatus.PENDING,
            )
            for quadrant in quadrants
        ])
        SourcingJob.objects.filter(pk=job_id).update(
            total_tiles=F('total_tiles') + len(children),
            completed_tiles=F('completed_tiles') + 1,
        )
        child_ids = [child.id for child in children]
        transaction.on_commit(
            lambda: group(
                fetch_tile.s(job_id=job_id, tile_id=child_id)
                for child_id in child_ids
            ).apply_async(),
        )

    logger.info(
        'sourcing.tile.split',
        job_id=job_id, tile_id=tile.pk, depth=tile.depth, child_count=len(children),
    )


def _upsert_hospital(item: dict) -> None:
    """Insert or update one Hospital row from a classified payload.

    Stamps `item['_persist_outcome']` so the surrounding loop can update
    counters without re-querying the DB.

    `.update()` calls pass `updated_at=Now()` explicitly — Django does not
    fire `auto_now=True` on a queryset `.update()`.
    """

    raw = item['raw']
    place_id = item['place_id']
    llm = item.get('llm_label') or {}
    rule = item.get('rule_label') or {}
    excluded_reason = item.get('excluded_reason')

    name = ((raw.get('displayName') or {}).get('text')) or ''
    components = _extract_address_components(raw)

    # Prefer `internationalPhoneNumber` (E.164-shaped) over the national
    # form; strip spaces / dashes / parens so it lands cleanly in
    # `phone_e164`, which BlandAI expects in E.164.
    raw_phone = raw.get('internationalPhoneNumber') or raw.get('nationalPhoneNumber') or ''
    phone_e164 = ''.join(c for c in raw_phone if c == '+' or c.isdigit()) or None

    latitude = (raw.get('location') or {}).get('latitude')
    longitude = (raw.get('location') or {}).get('longitude')
    phone_e164 = (phone_e164 or '')[:24] or None
    display_name: str = name[:200] or 'Unknown'

    defaults = {
        'name': display_name,
        'phone_e164': phone_e164,
        'website': (raw.get('websiteUri') or '')[:500] or None,
        'formatted_address': (raw.get('formattedAddress') or '')[:500] or None,
        'city': components.get('city'),
        'state': components.get('state'),
        'postal_code': components.get('postal_code'),
        'latitude': latitude,
        'longitude': longitude,
        'timezone': (raw.get('timeZone') or {}).get('id'),
    }

    # Practice-dedup merge (DRT-5297). A brand-new place_id that shares a
    # (non-toll-free) phone with an existing live practice is one of that
    # practice's per-vet listings — merge it into the canonical row instead of
    # creating a duplicate. Skipped for known place_ids (already canonical)
    # and for missing / toll-free numbers (not a reliable practice identity).
    existing = (
        Hospital.objects
        .filter(source=HospitalSource.GOOGLE_PLACES, source_external_id=place_id)
        .first()
    )
    # An excluded listing (closed / non-clinic) must NOT merge into an active
    # sibling — it would never reach the `excluded_reason` persistence path
    # below, inflating `merged_count`/`excluded_count` and polluting the active
    # row's `member_place_ids`. Skip the merge so it falls through to
    # get_or_create → excluded_reason recording.
    if existing is None and phone_e164 and not _is_toll_free(phone_e164) and not excluded_reason:
        merge_outcome = _try_merge_into_sibling(
            place_id=place_id,
            name=display_name,
            phone_e164=phone_e164,
            website=defaults['website'],
            formatted_address=defaults['formatted_address'],
            latitude=latitude,
            longitude=longitude,
        )
        # `'merged'` (newly absorbed, counts) or `'merged_noop'` (re-run, not
        # counted) both skip the create path; only `None` falls through.
        if merge_outcome is not None:
            item['_persist_outcome'] = merge_outcome
            return

    hospital, created = Hospital.objects.get_or_create(
        source=HospitalSource.GOOGLE_PLACES,
        source_external_id=place_id,
        defaults={**defaults, 'metadata': {}},
    )

    # Always refresh the staleness timestamp + basic Google fields, even
    # for locked rows. That's the "90-day refresh" rule from research §B5.
    metadata = dict(hospital.metadata or {})
    metadata['google_places_fetched_at'] = timezone.now().isoformat()
    if rule.get('chain_brand_normalized'):
        metadata['chain_brand_normalized'] = rule['chain_brand_normalized']

    if hospital.label_locked:
        # Operator hand-corrected this row — refresh contact / address
        # only, never the classification.
        Hospital.objects.filter(pk=hospital.pk).update(
            phone_e164=defaults['phone_e164'],
            website=defaults['website'],
            formatted_address=defaults['formatted_address'],
            metadata=metadata,
            updated_at=Now(),
        )
        item['_persist_outcome'] = 'skipped_locked'
        return

    if excluded_reason:
        # Non-clinic / closed: persist so re-runs skip it. `dispatch_schedule`
        # skips any row carrying an `excluded_reason`.
        Hospital.objects.filter(pk=hospital.pk).update(
            excluded_reason=excluded_reason[:200],
            metadata=metadata,
            updated_at=Now(),
        )
        item['_persist_outcome'] = 'inserted' if created else 'updated'
        return

    if llm.get('needs_review'):
        metadata['needs_review'] = True

    # Enum members are passed directly here (not `.value`): at runtime a
    # StrEnum member *is* a str, so the column write is identical.
    Hospital.objects.filter(pk=hospital.pk).update(
        ownership=item.get('suggested_ownership')
        or llm.get('ownership')
        or HospitalOwnership.UNCLASSIFIED,
        service_tags=llm.get('service_tags') or [],
        specialty_areas=llm.get('specialty_areas') or [],
        appointment_mode=llm.get('appointment_mode') or HospitalAppointmentMode.UNKNOWN,
        metadata=metadata,
        updated_at=Now(),
    )
    item['_persist_outcome'] = 'inserted' if created else 'updated'


def _extract_address_components(raw: dict) -> dict[str, str | None]:
    out: dict[str, str | None] = {'city': None, 'state': None, 'postal_code': None}
    for c in raw.get('addressComponents') or []:
        types = set(c.get('types') or [])
        if 'locality' in types and not out['city']:
            out['city'] = (c.get('shortText') or c.get('longText') or None)
            if out['city']:
                out['city'] = out['city'][:100]
        elif 'administrative_area_level_1' in types and not out['state']:
            out['state'] = (c.get('shortText') or c.get('longText') or None)
            if out['state']:
                out['state'] = out['state'][:2]
        elif 'postal_code' in types and not out['postal_code']:
            out['postal_code'] = (c.get('shortText') or c.get('longText') or None)
            if out['postal_code']:
                out['postal_code'] = out['postal_code'][:16]
    return out


@shared_task(name='sourcing.try_finalize', acks_late=True)
def try_finalize(*, job_id: int) -> dict:
    """Finalize the job once no tiles are left PENDING/RUNNING.

    `finalize_job` runs inline — its `filter(status=RUNNING).update()` is
    idempotent, so two `try_finalize` calls racing to the same conclusion
    transition the job exactly once.
    """

    job = _job_running(job_id)
    if job is None or job.status != SourcingJobStatus.RUNNING:
        return {'result': 'skipped'}

    has_unresolved = (
        SourcingTile.objects
        .filter(job_id=job_id, status__in=UNRESOLVED_TILE_STATUSES)
        .exists()
    )
    if has_unresolved:
        return {'result': 'pending_tiles'}

    return finalize_job(job_id=job_id)


def finalize_job(*, job_id: int) -> dict:
    """Idempotent job completion + partial-reason verdict.

    Partial-reason priority: call_limit > tile_failures > min_size_residual.
    `fetch_tile` already stamps `call_limit` when the call budget runs out;
    here we keep it and only fill the lower-priority reasons.
    """

    job = SourcingJob.objects.filter(pk=job_id).first()
    if job is None:
        return {'result': 'noop'}

    partial = job.partial
    partial_reason = job.partial_reason
    if not partial_reason:
        # `partial_reason` unset → call_limit didn't fire. Apply the
        # remaining reasons in priority order.
        if job.failed_tile_count > 0:
            partial = True
            partial_reason = PartialReason.TILE_FAILURES
        elif job.capped_tile_count > 0:
            partial = True
            partial_reason = PartialReason.MIN_SIZE_RESIDUAL

    updated = (
        SourcingJob.objects
        .filter(pk=job_id, status=SourcingJobStatus.RUNNING)
        .update(
            status=SourcingJobStatus.COMPLETED,
            completed_at=timezone.now(),
            partial=partial,
            partial_reason=partial_reason,
        )
    )
    logger.info(
        'sourcing.finalize_job',
        job_id=job_id, updated=updated, partial=partial, partial_reason=partial_reason,
    )
    return {'result': 'completed' if updated else 'noop'}
