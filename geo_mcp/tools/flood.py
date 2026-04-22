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

    Coverage is **England only**. For a Welsh, Scottish, or Northern Irish
    point the tool returns zone 1 by default (no polygon coverage), which
    is misleading; check the `region` / `country` context separately
    (e.g. via `reverse_geocode_uk`) before acting on this.

    Not included in this version (deferred to a later release):
      - surface-water flood risk (distinct EA dataset, RoFRS)
      - flags for whether the area is defended (Areas Benefiting from
        Defences dataset)

    Arguments:
        lat: WGS84 latitude, -90..90.
        lon: WGS84 longitude, -180..180.

    Returns `{zone: 1|2|3, source, coverage_note, attribution}`. On
    invalid input, returns `{"error": ..., "message": ...}`.
    """
    err = validate_wgs84(lat, lon)
    if err is not None:
        return err

    pool = await get_pool()
    async with pool.acquire() as conn:
        fz3 = await conn.fetchrow(_QUERY, lon, lat, "FZ3")
        if fz3 is not None:
            return _resp(3, fz3["flood_source"])
        fz2 = await conn.fetchrow(_QUERY, lon, lat, "FZ2")
        if fz2 is not None:
            return _resp(2, fz2["flood_source"])
    return _resp(1, None)


def _resp(zone: int, source: str | None) -> dict[str, Any]:
    return {
        "zone": zone,
        "source": source,  # 'Rivers' / 'Sea' / 'Rivers and Sea' / None for zone 1
        "coverage_note": (
            "Dataset covers England only. Points in Scotland, Wales, or "
            "Northern Ireland will return zone 1 here but are not actually "
            "assessed — use a country-specific flood dataset for those."
        ),
        "attribution": _ATTRIBUTION,
    }
