"""Rivers / watercourses lookup — OS Open Rivers."""
from __future__ import annotations

from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._validators import validate_radius_m, validate_wgs84

_ATTRIBUTION = (
    "Contains OS data © Crown copyright and database right 2026. OS Open "
    "Rivers is licensed under the Open Government Licence v3.0."
)

_DEFAULT_RADIUS_M = 500
_MAX_RADIUS_M = 10_000


async def river_nearby_uk(
    lat: float,
    lon: float,
    radius_m: int = _DEFAULT_RADIUS_M,
) -> dict[str, Any]:
    """Named watercourses within a radius of a UK point.

    Backed by OS Open Rivers — 193,000 watercourse link segments across
    GB, each tagged with name (where known), form (e.g. "lake", "river",
    "canal"), and flow direction. Useful for "is this property close
    to a river / canal / ditch" queries that feed flood context or
    waterside amenity claims.

    Coverage: **Great Britain**. Some segments are unnamed (minor
    streams, culverts); these are included in the count but may have
    a null name.

    Returns the **nearest named river** + up to 10 unique named
    watercourses within the radius (with the closest segment's
    distance).

    Arguments:
        lat, lon: WGS84.
        radius_m: 1–10000 m, default 500.

    Returns:
        {
          "center": {"lat", "lon", "radius_m"},
          "nearest": {
              "watercourse_name": "River Thames",
              "form": "river",
              "distance_m": 42.3
          } | null,
          "rivers": [
              {"watercourse_name", "form", "distance_m"},
              ...up to 10, sorted nearest
          ],
          "source": "OS Open Rivers",
          "attribution": "..."
        }
    """
    err = validate_wgs84(lat, lon) or validate_radius_m(radius_m, max_m=_MAX_RADIUS_M)
    if err is not None:
        return err

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH pt AS (
                SELECT ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 27700) AS g
            ), hits AS (
                SELECT DISTINCT ON (watercourse_name)
                       watercourse_name, form,
                       ST_Distance(r.geom_osgb, pt.g)::float8 AS distance_m
                  FROM staging.os_rivers r, pt
                 WHERE watercourse_name IS NOT NULL
                   AND ST_DWithin(r.geom_osgb, pt.g, $3)
                 ORDER BY watercourse_name, ST_Distance(r.geom_osgb, pt.g)
            )
            SELECT *
              FROM hits
             ORDER BY distance_m
             LIMIT 10
            """,
            lon, lat, radius_m,
        )

    rivers = [
        {
            "watercourse_name": r["watercourse_name"],
            "form": r["form"],
            "distance_m": round(float(r["distance_m"]), 1),
        }
        for r in rows
    ]
    return {
        "center": {"lat": round(lat, 6), "lon": round(lon, 6), "radius_m": radius_m},
        "nearest": rivers[0] if rivers else None,
        "rivers": rivers,
        "source": "OS Open Rivers",
        "attribution": _ATTRIBUTION,
    }
