from __future__ import annotations

from typing import Any

from geo_mcp.data_access.cog import open_cog
from geo_mcp.data_access.projections import to_osgb
from geo_mcp.tools._validators import validate_wgs84

_COG_NAME = "terrain50.tif"
_ATTRIBUTION = (
    "Contains OS data © Crown copyright and database right 2026. "
    "Licensed under the Open Government Licence v3.0."
)


async def elevation(
    points: list[dict[str, float]],
) -> dict[str, Any]:
    """Sample OS Terrain 50 elevation (metres above OSGB datum) at one or more WGS84 points.

    Pass a list of `{lat, lon}` objects. The tool reprojects each to British
    National Grid (EPSG:27700) and samples the 50m-resolution digital
    terrain model at the matching pixel. For a single point you get a
    single reading; for multiple points you get a profile suitable for
    drawing an elevation chart along a path.

    Elevation is metres above the OSGB36 vertical datum (≈ Newlyn tide
    gauge mean sea level). 50m horizontal resolution — the returned value
    is the best estimate for a 50×50 m cell, not a surveyed spot height.

    Coverage is **Great Britain** (England, Scotland, Wales, plus most
    offshore islands). Northern Ireland, the Isle of Man, the Channel
    Islands, and Ireland all return `{"elevation_m": null, "status":
    "out_of_coverage"}` — the dataset doesn't cover them.

    Arguments:
        points: list of `{lat: float, lon: float}` objects, WGS84.
                Typical usage: one point, or 2–200 points for a profile.
                Capped at 500 points per call to bound response size.

    Returns:
        {
            "points": [
                {"lat": ..., "lon": ..., "elevation_m": float | null, "status": "ok" | "out_of_coverage"},
                ...
            ],
            "source": "OS Terrain 50 (50m DTM)",
            "datum": "OSGB36 vertical (~mean sea level)",
            "attribution": "..."
        }

    On invalid input (empty list, >500 points, out-of-range coords),
    returns `{"error": ..., "message": ...}`.
    """
    if not isinstance(points, list) or not points:
        return {"error": "invalid_input", "message": "points must be a non-empty list."}
    if len(points) > 500:
        return {
            "error": "too_many_points",
            "message": f"Maximum 500 points per call, got {len(points)}.",
        }
    for p in points:
        lat, lon = p.get("lat"), p.get("lon")
        if lat is None or lon is None:
            return {"error": "invalid_point", "message": f"Each point needs lat and lon; got {p}."}
        err = validate_wgs84(lat, lon)
        if err is not None:
            return err

    ds = open_cog(_COG_NAME)
    nodata = ds.nodata
    transformer = to_osgb()

    results: list[dict[str, Any]] = []
    xs = [p["lon"] for p in points]
    ys = [p["lat"] for p in points]
    eastings, northings = transformer.transform(xs, ys)

    # ds.sample streams one value per input coord; much faster than N open/close cycles.
    samples = ds.sample(list(zip(eastings, northings, strict=True)), indexes=1)

    left, bottom, right, top = ds.bounds
    for p, e, n, sample in zip(points, eastings, northings, samples, strict=True):
        in_bounds = left <= e <= right and bottom <= n <= top
        value = float(sample[0]) if in_bounds else None
        is_nodata = nodata is not None and value is not None and value == nodata
        if not in_bounds or is_nodata:
            results.append({**p, "elevation_m": None, "status": "out_of_coverage"})
        else:
            results.append({**p, "elevation_m": round(value, 2), "status": "ok"})

    return {
        "points": results,
        "source": "OS Terrain 50 (50m DTM)",
        "datum": "OSGB36 vertical (~mean sea level)",
        "attribution": _ATTRIBUTION,
    }
