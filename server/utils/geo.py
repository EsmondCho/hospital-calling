"""Geographic helpers for the sourcing tile pipeline (DRT-5265 §4.5).

Pure functions — no Django / app imports. `utils` is the lowest layer
(`docs/architecture/layers.md`): it must not import app code.
"""

from __future__ import annotations

import math

# Meters per degree of latitude. Constant enough for tile-size decisions —
# the polar vs equatorial variation (~1%) is well within the slack of a
# 300m minimum-tile guardrail.
EARTH_METERS_PER_DEG_LAT = 111_320.0

# Mean Earth radius (meters) for the haversine great-circle distance. The
# sourcing practice-dedup proximity guard works at the ~250m scale, where the
# spherical-Earth approximation is more than precise enough.
EARTH_RADIUS_METERS = 6_371_000.0


def haversine_meters(*, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance (meters) between two lat/lng points.

    Standard haversine on a spherical Earth (`EARTH_RADIUS_METERS`). Used by
    the practice-dedup proximity guard to confirm two same-phone Google
    listings are physically the same clinic, not a shared call centre.
    """

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return EARTH_RADIUS_METERS * 2 * math.asin(math.sqrt(a))


def tile_edge_meters(*, south: float, west: float, north: float, east: float) -> float:
    """Shortest edge length (meters) of a tile bounding box.

    Used by the min-tile-size guardrail. Longitude degrees shrink with
    latitude: `111_320 * cos(lat)`. Returns the shorter of height / width
    so a tall-thin or wide-flat tile is still judged by its smallest side.
    """

    mid_lat_rad = math.radians((south + north) / 2)
    height_m = (north - south) * EARTH_METERS_PER_DEG_LAT
    width_m = (east - west) * EARTH_METERS_PER_DEG_LAT * math.cos(mid_lat_rad)
    return min(height_m, width_m)


def split_quadrants(
    *, south: float, west: float, north: float, east: float,
) -> list[dict[str, float]]:
    """Split a bounding box into NW / NE / SW / SE child boxes.

    The four children tile the parent exactly — no gaps, no overlap (each
    shares an edge with its neighbour at the midlines).
    """

    mid_lat = (south + north) / 2
    mid_lng = (west + east) / 2
    return [
        {'south': mid_lat, 'west': west, 'north': north, 'east': mid_lng},     # NW
        {'south': mid_lat, 'west': mid_lng, 'north': north, 'east': east},     # NE
        {'south': south, 'west': west, 'north': mid_lat, 'east': mid_lng},     # SW
        {'south': south, 'west': mid_lng, 'north': mid_lat, 'east': east},     # SE
    ]
