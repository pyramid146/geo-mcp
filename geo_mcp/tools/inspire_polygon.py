"""HMLR INSPIRE Index Polygon lookup — freehold title outline for a UK point.

Requires the staging.hmlr_inspire_polygons table to be populated. Until
you register with HMLR and drop the GML zips into /data/ingest/hmlr_inspire/raw/
the tool politely reports data_not_loaded. See ingest/hmlr_inspire/README.md
for the registration flow.
"""
from __future__ import annotations

import json
from typing import Any

from geo_mcp.data_access.postgis import get_pool

_ATTRIBUTION = (
    "Contains HM Land Registry INSPIRE Index Polygon data © Crown "
    "copyright and database right 2026. Licensed under the INSPIRE "
    "Index Polygons Licence (v2.0)."
)


async def title_polygon_uk(
    lat: float | None = None,
    lon: float | None = None,
) -> dict[str, Any]:
    """Freehold registered-title polygon containing a UK point.

    Backed by HMLR's INSPIRE Index Polygons — the legal-title boundary
    dataset for every registered freehold in England and Wales.

    Coverage is **England and Wales** (registered titles only — some
    Crown, church, and unregistered land is absent). Scotland / NI use
    separate land registries and are not included.

    Arguments:
        lat, lon: WGS84. Both required.

    Returns:
        {
          "point": {"lat", "lon"},
          "title": {
              "inspire_id": 12345,
              "la_code": "...",
              "update_date": "YYYY-MM-DD",
              "area_sqm": 453.2,
              "polygon_wgs84": {<GeoJSON Polygon|MultiPolygon>}
          } | null,
          "source": "HMLR INSPIRE Index Polygons",
          "attribution": "..."
        }

    ``title: null`` means the point doesn't fall inside any registered
    INSPIRE polygon (unregistered land, Crown land, gap in the dataset).
    """
    if lat is None or lon is None:
        return {"error": "invalid_input", "message": "lat and lon are both required."}

    pool = await get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT to_regclass('staging.hmlr_inspire_polygons')"
        )
        if exists is None:
            return {
                "error": "data_not_loaded",
                "message": (
                    "HMLR INSPIRE Index Polygons are not loaded on this server. "
                    "They require a free HMLR registration + manual bulk "
                    "download — see ingest/hmlr_inspire/README.md."
                ),
            }

        row = await conn.fetchrow(
            """
            WITH pt AS (
                SELECT ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 27700) AS g
            )
            SELECT h.inspire_id, h.la_code, h.update_date,
                   ST_Area(h.geom_osgb)::float8 AS area_sqm,
                   ST_AsGeoJSON(ST_Transform(h.geom_osgb, 4326), 6) AS polygon_geojson
              FROM staging.hmlr_inspire_polygons h, pt
             WHERE ST_Contains(h.geom_osgb, pt.g)
             LIMIT 1
            """,
            lon, lat,
        )

    if row is None:
        return {
            "point": {"lat": round(lat, 6), "lon": round(lon, 6)},
            "title": None,
            "note": "Point is not inside any registered INSPIRE polygon.",
            "source": "HMLR INSPIRE Index Polygons",
            "attribution": _ATTRIBUTION,
        }

    return {
        "point": {"lat": round(lat, 6), "lon": round(lon, 6)},
        "title": {
            "inspire_id": int(row["inspire_id"]),
            "la_code": row["la_code"],
            "update_date": row["update_date"].isoformat() if row["update_date"] else None,
            "area_sqm": round(float(row["area_sqm"]), 1),
            "polygon_wgs84": json.loads(row["polygon_geojson"]),
        },
        "source": "HMLR INSPIRE Index Polygons",
        "attribution": _ATTRIBUTION,
    }
