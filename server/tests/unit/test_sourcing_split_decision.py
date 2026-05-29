"""Unit tests for the sourcing cap / split decision logic (DRT-5265 §5.1).

The split decision is a pure predicate over three inputs:
  - cumulative `fetched_count` vs `SOURCING_SPLIT_THRESHOLD` (55),
  - tile `depth` vs the job's `max_depth`,
  - `tile_edge_meters` vs `SOURCING_MIN_TILE_METERS` (300).

`_advance_tile` in `tasks.py` wires these to DB rows; here we test the
arithmetic in isolation so the cap heuristic (==60 / 55-59 / <55) and the
guardrail cutoffs are pinned without a DB.
"""

from __future__ import annotations

from django.conf import settings

from utils.geo import tile_edge_meters


def _cap_suspected(fetched_count: int) -> bool:
    """No nextPageToken + cumulative results at/above the threshold."""

    return fetched_count >= settings.SOURCING_SPLIT_THRESHOLD


def _can_split(*, depth: int, max_depth: int, edge_meters: float) -> bool:
    return depth < max_depth and edge_meters > settings.SOURCING_MIN_TILE_METERS


# ---- cap-suspected heuristic ----------------------------------------------

def test_cap_suspected_at_exactly_60() -> None:
    """3 pages × 20 with no nextPageToken — the textbook cap hit."""

    assert _cap_suspected(60) is True


def test_cap_suspected_in_55_to_59_band() -> None:
    """55-59 is the conservative-split band: pageSize isn't guaranteed, so
    treat it as 'almost certainly truncated'."""

    for count in (55, 56, 57, 58, 59):
        assert _cap_suspected(count) is True


def test_cap_not_suspected_below_threshold() -> None:
    """< 55 → genuine end of results, no split."""

    for count in (0, 30, 54):
        assert _cap_suspected(count) is False


# ---- split-vs-residual guardrails -----------------------------------------

def test_can_split_when_within_depth_and_above_min_size() -> None:
    # A large box at shallow depth — splitting is allowed.
    edge = tile_edge_meters(south=37.0, west=-122.5, north=37.5, east=-122.0)
    assert edge > settings.SOURCING_MIN_TILE_METERS
    assert _can_split(depth=2, max_depth=6, edge_meters=edge) is True


def test_cannot_split_at_max_depth() -> None:
    edge = tile_edge_meters(south=37.0, west=-122.5, north=37.5, east=-122.0)
    assert _can_split(depth=6, max_depth=6, edge_meters=edge) is False


def test_cannot_split_below_min_tile_size() -> None:
    """A box whose edge is under 300m must not split even if cap-suspected —
    it becomes a capped_at_min_size residual instead."""

    # ~0.001° ≈ 111m edge — well below the 300m floor.
    edge = tile_edge_meters(south=37.0, west=-122.0, north=37.001, east=-121.999)
    assert edge < settings.SOURCING_MIN_TILE_METERS
    assert _can_split(depth=2, max_depth=6, edge_meters=edge) is False


def test_capped_residual_when_cap_suspected_but_cannot_split() -> None:
    """The min-size residual case: cap suspected (57 results) but the tile
    is too small to split → record the potential miss, don't recurse."""

    edge = tile_edge_meters(south=37.0, west=-122.0, north=37.001, east=-121.999)
    assert _cap_suspected(57) is True
    assert _can_split(depth=2, max_depth=6, edge_meters=edge) is False
