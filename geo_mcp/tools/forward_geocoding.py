from __future__ import annotations

from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._validators import canonical_spaced_postcode, is_valid_uk_postcode

_ATTRIBUTION = (
    "Contains OS data © Crown copyright and database right 2026 and "
    "ONS Postcode Directory data. Licensed under the Open Government Licence v3.0."
)

_POSTCODE_QUERY = """
SELECT pcds,
       lat::float8 AS lat,
       long::float8 AS lon,
       ctry25cd, rgn25cd, lad25cd
  FROM staging.onspd
 WHERE (pcds = $1 OR pcd7 = $2)
   AND doterm IS NULL
 LIMIT 1;
"""

# One query with two passes: populatedPlace-filtered first, then any-type
# fallback. We rank by local_type priority so "Manchester" gets the City,
# not a nearby Other Settlement.
_NAME_QUERY = """
WITH hits AS (
    SELECT name1, local_type, type,
           county_unitary, region, country, postcode_district,
           ST_Y(ST_Transform(geom, 4326))::float8 AS lat,
           ST_X(ST_Transform(geom, 4326))::float8 AS lon,
           CASE local_type
             WHEN 'City' THEN 1
             WHEN 'Town' THEN 2
             WHEN 'Village' THEN 3
             WHEN 'Hamlet' THEN 4
             WHEN 'Suburban Area' THEN 5
             ELSE 99
           END AS rank
      FROM staging.opennames
     WHERE lower(name1) = lower($1)
)
SELECT *, COUNT(*) OVER () AS total_matches
  FROM hits
 ORDER BY (type <> 'populatedPlace'), rank, name1
 LIMIT 6;
"""


async def geocode_uk(query: str) -> dict[str, Any]:
    """Forward-geocode a UK postcode or place name to WGS84 lat/lon.

    Accepts two kinds of query:

    1. **A UK postcode** in either spaced ("SW1A 1AA") or unspaced
       ("SW1A1AA") form, case-insensitive. Resolves against the ONS
       Postcode Directory and returns the ONS-canonical centroid for
       that postcode with `match_type: "postcode"`.

    2. **A place name** — populated place (city / town / village / hamlet),
       road, or any OpenNames feature. Case-insensitive exact match on
       OpenNames' NAME1 field. Populated places are preferred over other
       feature types; within populated places, cities rank above towns
       above villages above hamlets.

    If several features share the name (e.g. "Newport"), returns the best
    single match with `confidence: "multiple"` and an `alternatives` list
    carrying each candidate's admin context so the caller can
    disambiguate. If no match is found, returns `match_type: "none"`
    with null coordinates.

    Fuzzy matching, partial-string search, and multi-token address
    parsing ("10 Downing Street, London") are **not** supported in this
    version — exact name matches only. For address-level geocoding, fall
    back to `reverse_geocode_uk` starting from a nearby known point, or
    a commercial address provider.

    Arguments:
        query: the postcode or place name.

    Returns either:
        {"match_type": "postcode", "confidence": "exact", "lat", "lon",
         "query", "context": {postcode, country_code, region_code, lad_code},
         "source", "attribution"}
        {"match_type": "populated_place" | "feature", "confidence":
         "exact" | "multiple", "lat", "lon", "query", "context":
         {name, local_type, county_unitary, region, country,
         postcode_district}, "alternatives" (when multiple),
         "source", "attribution"}
        {"match_type": "none", "query", "message", "source": null}
    """
    if not isinstance(query, str) or not query.strip():
        return {"error": "invalid_input", "message": "query must be a non-empty string."}
    q = query.strip()
    pool = await get_pool()

    if is_valid_uk_postcode(q):
        return await _resolve_postcode(q, pool)
    return await _resolve_name(q, pool)


async def _resolve_postcode(q: str, pool) -> dict[str, Any]:
    spaced = canonical_spaced_postcode(q)
    unspaced = q.replace(" ", "").upper()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_POSTCODE_QUERY, spaced, unspaced)
    if row is None:
        return {
            "match_type": "none",
            "query": q,
            "message": "Query parsed as a postcode but not found in ONSPD.",
            "source": "ONSPD Feb 2026",
            "attribution": _ATTRIBUTION,
        }
    return {
        "match_type": "postcode",
        "confidence": "exact",
        "query": q,
        "lat": row["lat"],
        "lon": row["lon"],
        "context": {
            "postcode": row["pcds"],
            "country_code": row["ctry25cd"],
            "region_code": row["rgn25cd"],
            "local_authority_code": row["lad25cd"],
        },
        "source": "ONSPD Feb 2026",
        "attribution": _ATTRIBUTION,
    }


async def _resolve_name(q: str, pool) -> dict[str, Any]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(_NAME_QUERY, q)
    if not rows:
        return {
            "match_type": "none",
            "query": q,
            "message": "No exact match for that name in OpenNames.",
            "source": "OS OpenNames",
            "attribution": _ATTRIBUTION,
        }

    best = rows[0]
    match_type = "populated_place" if best["type"] == "populatedPlace" else "feature"
    total = int(best["total_matches"])
    confidence = "exact" if total == 1 else "multiple"

    resp: dict[str, Any] = {
        "match_type": match_type,
        "confidence": confidence,
        "query": q,
        "lat": best["lat"],
        "lon": best["lon"],
        "context": _context(best),
        "source": "OS OpenNames",
        "attribution": _ATTRIBUTION,
    }
    if confidence == "multiple":
        resp["alternatives"] = [
            {"lat": r["lat"], "lon": r["lon"], "context": _context(r)}
            for r in rows[1:]
        ]
    return resp


def _context(r) -> dict[str, Any]:
    return {
        "name": r["name1"],
        "local_type": r["local_type"],
        "feature_type": r["type"],
        "county_unitary": r["county_unitary"] or None,
        "region": r["region"] or None,
        "country": r["country"] or None,
        "postcode_district": r["postcode_district"] or None,
    }


