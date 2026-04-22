from __future__ import annotations

from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._validators import validate_wgs84

_ATTRIBUTION = (
    "Source: ONS (ONSPD), Ordnance Survey (Boundary-Line), and BGS (Geology "
    "625k / DiGMapGB-625), licensed under the Open Government Licence v3.0. "
    "Contains OS data © Crown copyright and database right 2026, Royal Mail "
    "data © Royal Mail copyright and database right 2026, GeoPlace data © "
    "Local Government Information House Limited copyright and database right 2026, "
    "BGS data © UKRI."
)

_QUERY = """
WITH input AS (
    SELECT ST_SetSRID(ST_MakePoint($1, $2), 4326) AS pt_wgs84,
           ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 27700) AS pt_osgb
),
nearest AS (
    SELECT o.pcds, o.pcd7,
           o.ctry25cd, o.rgn25cd, o.lad25cd, o.wd25cd, o.lsoa21cd, o.msoa21cd,
           ST_Distance(o.geom::geography, i.pt_wgs84::geography) AS distance_m
      FROM staging.onspd o, input i
     WHERE o.geom IS NOT NULL
       AND o.doterm IS NULL
     ORDER BY o.geom <-> i.pt_wgs84
     LIMIT 1
),
bedrock AS (
    SELECT b.lex_d AS bedrock_name, b.rcs_d AS bedrock_rock_type, b.gp_eq_d AS bedrock_group
      FROM staging.bgs_bedrock b, input i
     WHERE ST_Covers(b.geom, i.pt_osgb)
     LIMIT 1
),
superficial AS (
    SELECT s.lex_d AS superficial_name, s.rcs_d AS superficial_rock_type
      FROM staging.bgs_superficial s, input i
     WHERE ST_Covers(s.geom, i.pt_osgb)
     LIMIT 1
)
SELECT n.pcds, n.pcd7, n.distance_m,
       n.ctry25cd,  ac.name AS country_name,
       n.rgn25cd,   ar.name AS region_name,
       n.lad25cd,   al.name AS lad_name,
       n.wd25cd,    aw.name AS ward_name,
       n.lsoa21cd,
       n.msoa21cd,
       (SELECT bedrock_name      FROM bedrock)     AS bedrock_name,
       (SELECT bedrock_rock_type FROM bedrock)     AS bedrock_rock_type,
       (SELECT bedrock_group     FROM bedrock)     AS bedrock_group,
       (SELECT superficial_name      FROM superficial) AS superficial_name,
       (SELECT superficial_rock_type FROM superficial) AS superficial_rock_type
  FROM nearest n
  LEFT JOIN staging.admin_names ac ON ac.code = n.ctry25cd AND ac.level = 'country'
  LEFT JOIN staging.admin_names ar ON ar.code = n.rgn25cd  AND ar.level = 'region'
  LEFT JOIN staging.admin_names al ON al.code = n.lad25cd  AND al.level = 'lad'
  LEFT JOIN staging.admin_names aw ON aw.code = n.wd25cd   AND aw.level = 'ward';
"""


def _level(code: str | None, name: str | None) -> dict[str, Any] | None:
    if not code:
        return None
    return {"code": code, "name": name}


async def reverse_geocode_uk(
    lat: float,
    lon: float,
) -> dict[str, Any]:
    """Find the UK postcode nearest to a WGS84 latitude/longitude point, with
    its full administrative hierarchy (names and GSS codes).

    Returns the single closest live (non-terminated) postcode in the ONS
    Postcode Directory, its straight-line distance in metres, and the
    admin-area names (from OS Boundary-Line) and codes (from ONSPD) for
    country, region, local authority, and ward. LSOA and MSOA are returned
    as codes only — 2011/2021 census output areas have no name register.

    Use when a caller provides coordinates and needs "what postcode is this"
    or "what local authority is this in". For onshore UK points the result
    is typically within tens of metres of the source point. For points
    outside GB the result is still returned but distance_m will be large —
    check before trusting.

    Northern Ireland, the Isle of Man, and the Channel Islands are covered
    by postcodes (via ONSPD) but their admin names are not yet loaded —
    fields for country / region / local_authority / ward in those
    territories may return a code with a null name.

    Arguments:
        lat: WGS84 latitude in degrees, -90 .. 90.
        lon: WGS84 longitude in degrees, -180 .. 180.

    Returns a dict with keys `postcode`, `pcd7`, `distance_m`, `admin`
    (keyed by country / region / local_authority / ward / lsoa / msoa,
    each an object with `code` and `name`, or null if the code is empty),
    `source`, and `attribution`. On invalid input, returns
    `{"error": ..., "message": ...}`.
    """
    err = validate_wgs84(lat, lon)
    if err is not None:
        return err

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_QUERY, lon, lat)

    if row is None:
        return {"error": "no_match", "message": "No live UK postcode found."}

    geology: dict[str, Any] | None = None
    if row["bedrock_name"] is not None:
        geology = {
            "bedrock": {
                "formation_name": row["bedrock_name"],
                "rock_type": row["bedrock_rock_type"],
                "group": row["bedrock_group"] if row["bedrock_group"] and row["bedrock_group"] != "No Parent" else None,
            },
            "superficial": (
                {
                    "deposit_name": row["superficial_name"],
                    "rock_type": row["superficial_rock_type"] or None,
                }
                if row["superficial_name"] is not None else None
            ),
            "scale": "1:625,000 — regional interpretation, not for property-specific decisions",
        }

    return {
        "postcode": row["pcds"],
        "pcd7": row["pcd7"],
        "distance_m": round(float(row["distance_m"]), 2),
        "admin": {
            "country":         _level(row["ctry25cd"], row["country_name"]),
            "region":          _level(row["rgn25cd"],  row["region_name"]),
            "local_authority": _level(row["lad25cd"],  row["lad_name"]),
            "ward":            _level(row["wd25cd"],   row["ward_name"]),
            "lsoa":            _level(row["lsoa21cd"], None),
            "msoa":            _level(row["msoa21cd"], None),
        },
        "geology": geology,
        "source": "ONSPD Feb 2026 + OS Boundary-Line + BGS Geology 625k",
        "attribution": _ATTRIBUTION,
    }
