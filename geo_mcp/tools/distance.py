from __future__ import annotations

from typing import Any

from pyproj import Geod

from geo_mcp.data_access.projections import to_osgb

_GEOD = Geod(ellps="WGS84")


async def distance_between(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> dict[str, Any]:
    """Distance in metres between two WGS84 lat/lon points.

    Returns two distances:
      - `great_circle_m` — the geodesic distance on the WGS84 spheroid.
        This is the accurate "straight-line over the curved Earth"
        distance and works anywhere on the planet.
      - `projected_m` — Euclidean distance in the British National Grid
        (EPSG:27700) projection, in metres. For two UK points this is
        almost identical to the great-circle value; it's useful when the
        caller is reasoning about map-grid distances rather than true
        earth-surface distance. For points outside the UK the projection
        is undefined so `projected_m` is null.

    Use this when a caller asks "how far is A from B" — typically
    "distance from this postcode centroid to the nearest flood zone" or
    "how far is Manchester from Birmingham".

    Arguments:
        lat1, lon1: WGS84 coordinates of point A.
        lat2, lon2: WGS84 coordinates of point B.

    Returns `{great_circle_m, projected_m, azimuth_deg}` where
    `azimuth_deg` is the initial bearing from A to B (0 = north,
    clockwise). On invalid input, returns `{"error": ..., "message": ...}`.
    """
    for name, val in [("lat1", lat1), ("lat2", lat2)]:
        if not (-90.0 <= val <= 90.0):
            return {"error": f"invalid_{name}", "message": f"{name} must be in [-90, 90], got {val}."}
    for name, val in [("lon1", lon1), ("lon2", lon2)]:
        if not (-180.0 <= val <= 180.0):
            return {"error": f"invalid_{name}", "message": f"{name} must be in [-180, 180], got {val}."}

    fwd_az, _, geod_m = _GEOD.inv(lon1, lat1, lon2, lat2)

    # Projected distance — only meaningful if both points project to
    # finite OSGB coords (i.e. broadly UK-ish).
    transformer = to_osgb()
    x1, y1 = transformer.transform(lon1, lat1)
    x2, y2 = transformer.transform(lon2, lat2)
    if all(map(_finite, [x1, y1, x2, y2])):
        projected_m = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        projected_m = round(projected_m, 2)
    else:
        projected_m = None

    return {
        "great_circle_m": round(geod_m, 2),
        "projected_m": projected_m,
        "azimuth_deg": round(fwd_az % 360, 2),
    }


def _finite(v: float) -> bool:
    return v == v and v not in (float("inf"), float("-inf"))
