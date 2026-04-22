from __future__ import annotations

from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._validators import validate_radius_m, validate_wgs84

_ATTRIBUTION = (
    "Contains Historic England data © Historic England 2026. "
    "National Heritage List for England (NHLE). "
    "Licensed under the Open Government Licence v3.0."
)

_DEFAULT_RADIUS_M = 250
_MAX_RADIUS_M = 2_000
_MAX_RESULTS_RETURNED = 25

# Point-in-polygon, and within a small tolerance buffer for the point
# layer. A building listed as a point (no polygon extent surveyed) will
# sit ~on its rooftop coordinate; give a few metres of tolerance so the
# caller's own coord doesn't need to be pixel-perfect.
_IS_LISTED_QUERY = """
WITH pt AS (
    SELECT ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 27700) AS g
)
SELECT listentry::bigint, name, grade, designation_date, hyperlink,
       'polygon' AS match_type
  FROM staging.nhle_listed_polygons p, pt
 WHERE ST_Covers(p.geom, pt.g)
 UNION ALL
SELECT listentry::bigint, name, grade, designation_date, hyperlink,
       'point_within_tolerance'
  FROM staging.nhle_listed_points p, pt
 WHERE ST_DWithin(p.geom, pt.g, $3)
 ORDER BY 6 DESC  -- prefer polygon matches
 LIMIT 3;
"""

# heritage_nearby: count + nearest across all designation types.
_HERITAGE_NEARBY_SQL = """
WITH pt AS (
    SELECT ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 27700) AS g
),
hits AS (
    SELECT 'listed_building' AS designation, listentry::bigint AS list_entry,
           name, grade AS grade_or_null, designation_date, hyperlink,
           ST_Distance(geom, (SELECT g FROM pt))::float8 AS distance_m
      FROM staging.nhle_listed_polygons
     WHERE ST_DWithin(geom, (SELECT g FROM pt), $3)
    UNION ALL
    SELECT 'scheduled_monument', listentry::bigint, name, NULL,
           designation_date, hyperlink,
           ST_Distance(geom, (SELECT g FROM pt))::float8
      FROM staging.nhle_scheduled_monuments
     WHERE ST_DWithin(geom, (SELECT g FROM pt), $3)
    UNION ALL
    SELECT 'park_or_garden', listentry::bigint, name, grade,
           designation_date, hyperlink,
           ST_Distance(geom, (SELECT g FROM pt))::float8
      FROM staging.nhle_parks_and_gardens
     WHERE ST_DWithin(geom, (SELECT g FROM pt), $3)
    UNION ALL
    SELECT 'battlefield', listentry::bigint, name, NULL,
           designation_date, hyperlink,
           ST_Distance(geom, (SELECT g FROM pt))::float8
      FROM staging.nhle_battlefields
     WHERE ST_DWithin(geom, (SELECT g FROM pt), $3)
    UNION ALL
    SELECT 'protected_wreck', listentry::bigint, name, NULL,
           designation_date, hyperlink,
           ST_Distance(geom, (SELECT g FROM pt))::float8
      FROM staging.nhle_protected_wrecks
     WHERE ST_DWithin(geom, (SELECT g FROM pt), $3)
    UNION ALL
    SELECT 'world_heritage_site', listentry::bigint, name, NULL,
           designation_date, hyperlink,
           ST_Distance(geom, (SELECT g FROM pt))::float8
      FROM staging.nhle_world_heritage_sites
     WHERE ST_DWithin(geom, (SELECT g FROM pt), $3)
)
SELECT designation, list_entry, name, grade_or_null AS grade,
       designation_date, hyperlink, ROUND(distance_m::numeric, 2) AS distance_m
  FROM hits
 ORDER BY distance_m
 LIMIT $4;
"""


async def is_listed_building_uk(
    lat: float,
    lon: float,
    tolerance_m: int = 30,
) -> dict[str, Any]:
    """Check whether a WGS84 point sits on a listed building (NHLE designation).

    A listed building is a structure in England that's been formally
    designated by Historic England as of special architectural or
    historic interest. Listing is grade I (highest), II*, or II
    (majority). It's a significant legal status: you need Listed
    Building Consent for any alteration that would affect character,
    and penalties for unauthorised works are serious.

    The check is two-stage:
      1. Is the point inside any listed-building polygon? (the strongest
         signal — applies to any listing where a building footprint has
         been surveyed).
      2. Otherwise, is the point within ``tolerance_m`` of a listed-
         building *point*? (many historic listings are recorded as a
         single NGR point near the building centroid, without an
         explicit extent — the point can be tens of metres away from
         the actual facade for large structures like cathedrals).

    ``tolerance_m`` defaults to 30 m because the NHLE point is often not
    at the exact building coordinate — cathedrals / churches / country
    houses can have their listed-building point 20+ m from any lat/lon
    a caller would sensibly pass. A tight tolerance produced false
    negatives for e.g. York Minster, Buckingham Palace, Tower of London.
    Raise to 50–80 m for building-scale ambiguity; drop below 20 m if
    you need a stricter "is THIS exact point a listing" check.

    Use this when a caller is specifically asking about a property:
    "is this house listed?", "is this a listed building?" For broader
    heritage context at an area, use ``heritage_nearby_uk``.

    Coverage is **England only** (Historic England's remit). Welsh,
    Scottish, and NI historic environment bodies maintain their own
    registers: Cadw, HES, HED. A ``false`` answer here doesn't prove
    a UK-wide "not listed".

    Arguments:
        lat: WGS84 latitude.
        lon: WGS84 longitude.
        tolerance_m: fallback buffer around point-only listings (default 10 m).

    Returns:
        {
          "is_listed": bool,
          "matches": [
              {"list_entry", "name", "grade",
               "designation_date", "hyperlink", "match_type"},
              ...  # max 3; empty when not listed
          ],
          "coverage_note": "England only. ...",
          "source": "Historic England NHLE",
          "attribution": "..."
        }
    """
    err = validate_wgs84(lat, lon)
    if err is not None:
        return err
    if tolerance_m < 0 or tolerance_m > 100:
        return {
            "error": "invalid_tolerance",
            "message": f"tolerance_m must be in 0..100, got {tolerance_m}.",
        }

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_IS_LISTED_QUERY, lon, lat, tolerance_m)

    matches = [
        {
            "list_entry": int(r["listentry"]),
            "name": r["name"],
            "grade": r["grade"],
            "designation_date": r["designation_date"].isoformat() if r["designation_date"] else None,
            "hyperlink": r["hyperlink"],
            "match_type": r["match_type"],
        }
        for r in rows
    ]
    return {
        "is_listed": bool(matches),
        "matches": matches,
        "coverage_note": (
            "NHLE covers England only. A false result doesn't prove the building "
            "isn't designated in Wales (Cadw), Scotland (HES) or Northern Ireland (HED)."
        ),
        "source": "Historic England NHLE",
        "attribution": _ATTRIBUTION,
    }


async def heritage_nearby_uk(
    lat: float,
    lon: float,
    radius_m: int = _DEFAULT_RADIUS_M,
) -> dict[str, Any]:
    """List NHLE heritage designations within a radius of a WGS84 point.

    Returns the combined set of listed buildings + scheduled monuments +
    registered parks & gardens + battlefields + protected wrecks + world
    heritage sites that intersect a buffer of ``radius_m`` around the
    input point.

    This is the "what heritage context is nearby?" question — distinct
    from ``is_listed_building_uk`` which is the narrow "is this specific
    structure listed?" check. Use for planning / development screening,
    heritage-statement scoping, or to answer "are there any heritage
    constraints near this plot?".

    Coverage is **England only**.

    Arguments:
        lat: WGS84 latitude.
        lon: WGS84 longitude.
        radius_m: search radius in metres (default 250, max 2000).

    Returns:
        {
          "center": {"lat", "lon", "radius_m"},
          "count_by_type": {"listed_building": 12, "scheduled_monument": 0, ...},
          "total": int,
          "nearest": {designation, list_entry, name, ..., distance_m} | null,
          "designations": [...up to 25 nearest, full detail...],
          "source": "Historic England NHLE",
          "attribution": "..."
        }
    """
    err = validate_wgs84(lat, lon) or validate_radius_m(radius_m, max_m=_MAX_RADIUS_M)
    if err is not None:
        return err

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            _HERITAGE_NEARBY_SQL, lon, lat, radius_m, _MAX_RESULTS_RETURNED * 4,
        )

    designations: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for r in rows:
        d = r["designation"]
        counts[d] = counts.get(d, 0) + 1
        if len(designations) < _MAX_RESULTS_RETURNED:
            designations.append({
                "designation": d,
                "list_entry": int(r["list_entry"]) if r["list_entry"] is not None else None,
                "name": r["name"],
                "grade": r["grade"],
                "designation_date": r["designation_date"].isoformat() if r["designation_date"] else None,
                "hyperlink": r["hyperlink"],
                "distance_m": float(r["distance_m"]),
            })

    nearest = designations[0] if designations else None
    return {
        "center": {"lat": lat, "lon": lon, "radius_m": radius_m},
        "count_by_type": counts,
        "total": sum(counts.values()),
        "nearest": nearest,
        "designations": designations,
        "coverage_note": "NHLE covers England only.",
        "source": "Historic England NHLE",
        "attribution": _ATTRIBUTION,
    }
