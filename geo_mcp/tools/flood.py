from __future__ import annotations

from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._validators import validate_wgs84

_ATTRIBUTION = (
    "Contains Environment Agency data © Environment Agency copyright and/or "
    "database right 2025. Licensed under the Open Government Licence v3.0."
)

# Reproject the WGS84 input point once, then short-circuit on the first polygon
# that covers it. FZ3 is checked first (higher risk, smaller cardinality).
_QUERY = """
WITH pt AS (
    SELECT ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 27700) AS g
)
SELECT z.flood_zone, z.flood_source
  FROM staging.ea_flood_zones z, pt
 WHERE z.flood_zone = $3
   AND ST_Covers(z.geom, pt.g)
 LIMIT 1;
"""

# Is the point inside the England country boundary (OS Boundary-Line)?
# Used to distinguish a genuine Zone 1 from an out-of-coverage point —
# the EA's Flood Map for Planning only covers England, so a missing
# polygon could mean "low risk in England" or "outside the dataset".
_IN_ENGLAND_QUERY = """
WITH pt AS (
    SELECT ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 27700) AS g
)
SELECT 1
  FROM staging.bl_country, pt
 WHERE code = 'E92000001'
   AND ST_Covers(geom, pt.g)
 LIMIT 1;
"""


async def flood_risk_uk(
    lat: float,
    lon: float,
) -> dict[str, Any]:
    """Return the Environment Agency Flood Zone (1, 2, or 3) for a WGS84 point in England.

    This is the same dataset a Local Planning Authority consults to decide
    whether a planning application needs a Flood Risk Assessment.

    Zone meanings (EA Flood Map for Planning):
      3  — ≥1% (1 in 100) annual probability of river flooding, or
           ≥0.5% (1 in 200) annual probability of sea flooding. Highest risk.
      2  — 0.1%–1% from rivers, or 0.1%–0.5% from the sea. Moderate risk.
      1  — everything else. <0.1% annual probability. Lowest risk.

    The tool checks Zone 3 coverage first, then Zone 2. `source` tells you
    whether the zone is driven by rivers, sea, or both — values are the
    EA's raw strings: `river`, `sea`, `river and sea`, `river / undefined`,
    `undefined`, `unknown`, or null for zone 1 / no coverage.

    Coverage is **England only**. For a point in Scotland, Wales, or
    Northern Ireland the tool returns ``{verdict: "coverage_gap", zone: null}``
    — an explicit signal that the EA dataset doesn't apply, not a false
    Zone 1. Use a country-specific flood dataset (NRW / SEPA / DAERA)
    for those.

    Not included in this version (deferred to a later release):
      - surface-water flood risk (distinct EA dataset, RoFSW)
      - flags for whether the area is defended (Areas Benefiting from
        Defences dataset)

    Arguments:
        lat: WGS84 latitude, -90..90.
        lon: WGS84 longitude, -180..180.

    Returns (England point):
        ``{verdict: "ok", zone: 1|2|3, source, coverage_note, attribution}``

    Returns (non-England point):
        ``{verdict: "coverage_gap", zone: null, source: null,
           coverage_note: ..., attribution}``

    On invalid input, returns ``{"error": ..., "message": ...}``.
    """
    err = validate_wgs84(lat, lon)
    if err is not None:
        return err

    pool = await get_pool()
    async with pool.acquire() as conn:
        fz3 = await conn.fetchrow(_QUERY, lon, lat, "FZ3")
        if fz3 is not None:
            return _zone_resp(3, fz3["flood_source"])
        fz2 = await conn.fetchrow(_QUERY, lon, lat, "FZ2")
        if fz2 is not None:
            return _zone_resp(2, fz2["flood_source"])
        # No polygon hit. Distinguish "genuine Zone 1 in England" from
        # "outside the dataset's coverage" by checking the England
        # country polygon.
        in_england = await conn.fetchval(_IN_ENGLAND_QUERY, lon, lat)
    if in_england:
        return _zone_resp(1, None)
    return _coverage_gap_resp()


def _zone_resp(zone: int, source: str | None) -> dict[str, Any]:
    return {
        "verdict": "ok",
        "zone": zone,
        "source": source,  # 'river' / 'sea' / 'river and sea' / None for zone 1
        "coverage_note": (
            "Dataset covers England only. Points outside England are "
            "reported as coverage_gap rather than falling through to Zone 1."
        ),
        "attribution": _ATTRIBUTION,
    }


def _coverage_gap_resp() -> dict[str, Any]:
    return {
        "verdict": "coverage_gap",
        "zone": None,
        "source": None,
        "coverage_note": (
            "Point lies outside England. The EA Flood Map for Planning "
            "only covers England. For Wales use Natural Resources Wales' "
            "flood map; for Scotland use SEPA; for Northern Ireland use "
            "DAERA."
        ),
        "attribution": _ATTRIBUTION,
    }
