"""OS Open Greenspace lookup — parks, playing fields, allotments, etc."""
from __future__ import annotations

from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._validators import validate_radius_m, validate_wgs84

_ATTRIBUTION = (
    "Contains OS data © Crown copyright and database right 2026. OS Open "
    "Greenspace is licensed under the Open Government Licence v3.0."
)

_DEFAULT_RADIUS_M = 500
_MAX_RADIUS_M = 5_000
_MAX_RESULTS = 25

_VALID_FUNCTIONS = frozenset({
    "Play Space", "Religious Grounds", "Public Park Or Garden",
    "Playing Field", "Other Sports Facility",
    "Allotments Or Community Growing Spaces", "Cemetery",
    "Tennis Court", "Bowling Green", "Golf Course",
})


async def green_space_nearby_uk(
    lat: float,
    lon: float,
    radius_m: int = _DEFAULT_RADIUS_M,
    functions: list[str] | None = None,
) -> dict[str, Any]:
    """Public greenspaces within a radius of a UK point.

    Covers the 10 function types in OS Open Greenspace: Public Park or
    Garden, Play Space, Playing Field, Allotments, Cemetery, Religious
    Grounds, Golf Course, Bowling Green, Tennis Court, Other Sports
    Facility. Useful for "how green is this neighbourhood?",
    amenity-access scoring, and property quality-of-life context.

    Coverage: **Great Britain**. Northern Ireland is out of scope for
    OS Open Greenspace.

    Arguments:
        lat, lon: WGS84.
        radius_m: 1–5000 m, default 500.
        functions: optional list to filter by greenspace type.
            Passing e.g. ``["Public Park Or Garden", "Cemetery"]`` limits
            the results.

    Returns:
        {
          "center": {"lat", "lon", "radius_m"},
          "total": int,
          "count_by_function": {...},
          "greenspaces": [
              {"function", "name", "distance_m", "area_sqm"},
              ...up to 25 nearest
          ],
          "source": "OS Open Greenspace",
          "attribution": "..."
        }
    """
    err = validate_wgs84(lat, lon) or validate_radius_m(radius_m, max_m=_MAX_RADIUS_M)
    if err is not None:
        return err

    filter_functions: list[str] | None = None
    if functions is not None:
        if not isinstance(functions, list) or not all(isinstance(t, str) for t in functions):
            return {"error": "invalid_functions", "message": "functions must be a list of strings."}
        bad = [t for t in functions if t not in _VALID_FUNCTIONS]
        if bad:
            return {
                "error": "invalid_functions",
                "message": f"Unknown greenspace functions: {bad!r}. Valid: {sorted(_VALID_FUNCTIONS)}.",
            }
        filter_functions = functions

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH pt AS (
                SELECT ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 27700) AS g
            )
            SELECT function, distinctive_name_1 AS name,
                   ST_Distance(g.geom_osgb, pt.g)::float8 AS distance_m,
                   g.area_sqm
              FROM staging.os_greenspace g, pt
             WHERE ST_DWithin(g.geom_osgb, pt.g, $3)
               AND ($4::text[] IS NULL OR g.function = ANY($4))
             ORDER BY ST_Distance(g.geom_osgb, pt.g)
             LIMIT $5
            """,
            lon, lat, radius_m, filter_functions, _MAX_RESULTS,
        )

    greenspaces = [
        {
            "function": r["function"],
            "name": r["name"],
            "distance_m": round(float(r["distance_m"]), 1),
            "area_sqm": round(float(r["area_sqm"]), 0) if r["area_sqm"] is not None else None,
        }
        for r in rows
    ]
    by_fn: dict[str, int] = {}
    for g in greenspaces:
        by_fn[g["function"]] = by_fn.get(g["function"], 0) + 1

    return {
        "center": {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "radius_m": radius_m,
        },
        "total": len(greenspaces),
        "count_by_function": by_fn,
        "greenspaces": greenspaces,
        "source": "OS Open Greenspace",
        "attribution": _ATTRIBUTION,
    }
