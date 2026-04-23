"""Building footprint lookup by UPRN — backed by OS Open Zoomstack.

Closes the long-standing gap between "I have a UPRN" and "I have the
actual polygon outline of that property". Used standalone or chained
into property_report_uk for richer reports.
"""
from __future__ import annotations

import json
from typing import Any

from geo_mcp.data_access.postgis import get_pool

_ATTRIBUTION = (
    "Contains OS data © Crown copyright and database right 2026. Building "
    "footprints from OS Open Zoomstack and the UPRN→coordinate anchor "
    "from OS Open UPRN, both licensed under the Open Government Licence v3.0."
)


async def building_footprint_uk(uprn: int | str) -> dict[str, Any]:
    """Building polygon footprint for a UK UPRN.

    Looks up the UPRN's coordinate in OS Open UPRN, then finds the
    OS Open Zoomstack building polygon that contains that point.

    Returns the building footprint as GeoJSON (in WGS84 — ready to drop
    into a Mapbox / Leaflet / OpenLayers map), plus the OSGB easting /
    northing extent, the building's stable OS uuid, and the footprint
    area in square metres.

    Why this matters: most property workflows treat a UPRN as a point.
    The polygon footprint unlocks "what's the floor area", "draw this
    on a map", "is this near another feature" without needing to license
    AddressBase or MasterMap.

    Edge cases:
      * **UPRN points are anonymised to street level** for some classes
        of property (flats, etc.). The UPRN coord may not fall inside
        any building polygon — if so the response carries
        ``polygon: null`` along with the resolved UPRN coord, so the
        caller can still place the property on a map.
      * Coverage: **Great Britain** for both source datasets. NI UPRNs
        return ``error: "uprn_not_found"`` (LPS-assigned, out of OS
        Open UPRN's coverage).

    Arguments:
        uprn: integer or numeric string, 1–12 digits.

    Returns:
        {
          "uprn": 10033544614,
          "point": {"lat": 51.50101, "lon": -0.14156},
          "building": {
              "uuid": "abc-123-...",
              "area_sqm": 142.7,
              "bbox_osgb": {"min_easting", "min_northing", "max_easting", "max_northing"},
              "polygon_wgs84": {<GeoJSON Polygon | MultiPolygon>}
          } | null,
          "source": "OS Open Zoomstack",
          "attribution": "..."
        }

    On invalid UPRN returns ``{"error": "invalid_uprn", "message": ...}``.
    On unknown UPRN returns ``{"error": "uprn_not_found", "message": ...}``.
    """
    s = str(uprn).strip()
    if not s.isdigit():
        return {"error": "invalid_uprn", "message": f"UPRN must be numeric, got {uprn!r}."}
    if not 1 <= len(s) <= 12:
        return {"error": "invalid_uprn", "message": "UPRN must be 1–12 digits."}

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            WITH p AS (
                SELECT uprn, easting, northing, lat, lon,
                       ST_SetSRID(ST_MakePoint(easting, northing), 27700) AS pt
                  FROM staging.os_open_uprn
                 WHERE uprn = $1
            )
            SELECT
                p.uprn, p.lat, p.lon, p.easting, p.northing,
                b.uuid               AS building_uuid,
                b.area_sqm           AS building_area_sqm,
                ST_AsGeoJSON(ST_Transform(b.geom_osgb, 4326), 6) AS building_geojson,
                ST_XMin(b.geom_osgb) AS bb_min_e,
                ST_YMin(b.geom_osgb) AS bb_min_n,
                ST_XMax(b.geom_osgb) AS bb_max_e,
                ST_YMax(b.geom_osgb) AS bb_max_n
              FROM p
              LEFT JOIN staging.os_zoomstack_buildings b
                ON ST_Contains(b.geom_osgb, p.pt)
             LIMIT 1
            """,
            int(s),
        )

    if row is None:
        return {
            "error": "uprn_not_found",
            "message": (
                f"UPRN {s} not in OS Open UPRN. Either it doesn't exist, "
                f"is Northern Irish (out of coverage), or the dataset "
                f"is older than the UPRN's assignment date."
            ),
        }

    out: dict[str, Any] = {
        "uprn": int(row["uprn"]),
        "point": {"lat": round(float(row["lat"]), 6), "lon": round(float(row["lon"]), 6)},
        "building": None,
        "source": "OS Open Zoomstack",
        "attribution": _ATTRIBUTION,
    }
    if row["building_uuid"] is None:
        # Common when a UPRN sits on a footpath / car park / gate rather
        # than the building itself — flat/maisonette UPRNs especially.
        out["note"] = (
            "OS Open UPRN coordinate does not fall inside any OS Open "
            "Zoomstack building polygon — common for flats, gated "
            "properties, or addresses anonymised to a street centroid."
        )
        return out

    out["building"] = {
        "uuid": row["building_uuid"],
        "area_sqm": round(float(row["building_area_sqm"]), 1),
        "bbox_osgb": {
            "min_easting":  round(float(row["bb_min_e"]), 2),
            "min_northing": round(float(row["bb_min_n"]), 2),
            "max_easting":  round(float(row["bb_max_e"]), 2),
            "max_northing": round(float(row["bb_max_n"]), 2),
        },
        "polygon_wgs84": json.loads(row["building_geojson"]),
    }
    return out
