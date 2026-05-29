"""Unit tests for the sourcing tile geometry helpers (DRT-5265 §5.1).

Pure functions — no DB, no Celery.
"""

from __future__ import annotations

import math

from utils.geo import (
    EARTH_METERS_PER_DEG_LAT,
    haversine_meters,
    split_quadrants,
    tile_edge_meters,
)

# ---- tile_edge_meters ------------------------------------------------------

def test_tile_edge_meters_equator_square_is_latitude_bound() -> None:
    """At the equator cos(lat)≈1, so a 0.01°x0.01° box is ~square; the
    shorter edge is within rounding of the latitude-derived height."""

    edge = tile_edge_meters(south=0.0, west=0.0, north=0.01, east=0.01)
    expected = 0.01 * EARTH_METERS_PER_DEG_LAT
    # cos(0.005°) is fractionally below 1, so width is the (barely) shorter
    # side — equal to the height to 4 significant figures.
    assert math.isclose(edge, expected, rel_tol=1e-6)


def test_tile_edge_meters_high_latitude_width_shrinks() -> None:
    """At 60°N a degree of longitude is ~half a degree of latitude, so the
    width is the shorter edge for a box equal in degrees."""

    edge = tile_edge_meters(south=60.0, west=0.0, north=60.01, east=0.01)
    mid_lat_rad = math.radians(60.005)
    expected_width = 0.01 * EARTH_METERS_PER_DEG_LAT * math.cos(mid_lat_rad)
    assert math.isclose(edge, expected_width, rel_tol=1e-9)
    # Width must be the binding (shorter) dimension up north.
    height = 0.01 * EARTH_METERS_PER_DEG_LAT
    assert edge < height


def test_tile_edge_meters_returns_shortest_side() -> None:
    """A wide-flat box is judged by its (short) height."""

    edge = tile_edge_meters(south=10.0, west=0.0, north=10.001, east=0.5)
    height = 0.001 * EARTH_METERS_PER_DEG_LAT
    assert math.isclose(edge, height, rel_tol=1e-9)


# ---- split_quadrants -------------------------------------------------------

def test_split_quadrants_produces_four_children() -> None:
    children = split_quadrants(south=0.0, west=0.0, north=2.0, east=2.0)
    assert len(children) == 4


def test_split_quadrants_children_tile_parent_without_gaps() -> None:
    """The 4 children must exactly cover the parent — touching at the
    midlines, no gap, no overlap."""

    children = split_quadrants(south=0.0, west=0.0, north=2.0, east=2.0)
    nw, ne, sw, se = children

    # Midlines.
    assert nw['south'] == ne['south'] == 1.0
    assert sw['north'] == se['north'] == 1.0
    assert nw['east'] == sw['east'] == 1.0
    assert ne['west'] == se['west'] == 1.0

    # Outer extent matches the parent box.
    assert nw['west'] == sw['west'] == 0.0
    assert ne['east'] == se['east'] == 2.0
    assert nw['north'] == ne['north'] == 2.0
    assert sw['south'] == se['south'] == 0.0


def test_split_quadrants_union_area_equals_parent() -> None:
    parent_area = (2.0 - 0.0) * (2.0 - 0.0)
    children = split_quadrants(south=0.0, west=0.0, north=2.0, east=2.0)
    child_area = sum(
        (c['north'] - c['south']) * (c['east'] - c['west']) for c in children
    )
    assert math.isclose(child_area, parent_area, rel_tol=1e-9)


# ---- haversine_meters ------------------------------------------------------

def test_haversine_meters_identical_points_is_zero() -> None:
    """Distance between a point and itself is exactly 0."""

    dist = haversine_meters(lat1=37.7749, lng1=-122.4194, lat2=37.7749, lng2=-122.4194)
    assert dist == 0.0


def test_haversine_meters_one_degree_latitude() -> None:
    """One degree of latitude is ~111.32 km; haversine should land within a
    few percent of `EARTH_METERS_PER_DEG_LAT`."""

    dist = haversine_meters(lat1=0.0, lng1=0.0, lat2=1.0, lng2=0.0)
    assert math.isclose(dist, EARTH_METERS_PER_DEG_LAT, rel_tol=0.01)


def test_haversine_meters_short_distance_within_merge_radius_scale() -> None:
    """Two points ~0.001° apart in latitude are ~111m apart — the scale the
    250m practice-merge radius operates at."""

    dist = haversine_meters(lat1=40.0, lng1=-74.0, lat2=40.001, lng2=-74.0)
    # 0.001° latitude ≈ 111.32m.
    assert math.isclose(dist, 111.32, rel_tol=0.02)
