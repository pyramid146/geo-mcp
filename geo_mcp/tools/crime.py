"""Street-level crime lookup for the UK (England, Wales, NI).

Backed by data.police.uk's rolling monthly archive. 14 crime categories,
anonymised to street-level coordinates. Scotland is out of coverage —
Police Scotland doesn't contribute.
"""
from __future__ import annotations

from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._validators import validate_radius_m, validate_wgs84

_ATTRIBUTION = (
    "Contains information provided by the police forces of England, Wales "
    "and Northern Ireland via data.police.uk, licensed under the Open "
    "Government Licence v3.0. Crime locations are anonymised to a "
    "street-level point and may not precisely represent where an incident "
    "occurred."
)

_DEFAULT_RADIUS_M = 500
_MAX_RADIUS_M = 5_000
_DEFAULT_MONTHS = 12
_MAX_MONTHS = 36


async def crime_nearby_uk(
    lat: float,
    lon: float,
    radius_m: int = _DEFAULT_RADIUS_M,
    months: int = _DEFAULT_MONTHS,
) -> dict[str, Any]:
    """Recorded crime incidents within a radius of a UK lat/lon.

    Returns counts + breakdowns from the police.uk street-level archive —
    every crime reported to one of the 44 participating forces, placed
    at its (anonymised) street point. Useful for property-risk
    workflows ("is this a safe area?"), area-context queries, and
    insurance / letting decisions.

    Coverage:
      * England, Wales — full coverage
      * Northern Ireland — covered (PSNI contributes)
      * Scotland — **not covered** (Police Scotland doesn't contribute).
        Queries against Scottish points return count=0 with
        ``coverage_note`` flagging the gap.

    Caveats that matter to the caller:
      * **Street-level anonymisation**: locations are snapped to the
        nearest of ~750k anonymous "snap points" on streets/footways.
        An incident you get here was *somewhere in the vicinity* of
        the returned coord, not at it.
      * **14 crime categories**: violence and sexual offences, ASB,
        shoplifting, criminal damage and arson, public order, burglary,
        vehicle crime, theft from the person, drugs, bicycle theft,
        other theft, possession of weapons, robbery, other crime.
      * **~6-8 week reporting lag** — the most recent months in the
        window will typically lag real-time by that much.
      * **Volume ≠ risk**. A busy high-street has more shoplifting
        than a quiet lane; interpret in context.

    Arguments:
        lat, lon: WGS84.
        radius_m: 1–5000 m, default 500.
        months: 1–36, default 12 (most recent months in the archive).

    Returns:
        {
          "center": {"lat", "lon", "radius_m", "months_window"},
          "count": int,
          "by_crime_type": {"Violence and sexual offences": 42, ...},
          "by_month": [{"month": "2025-01", "count": 5}, ...],
          "coverage_note": null | string,
          "source": "data.police.uk",
          "attribution": "..."
        }
    """
    err = validate_wgs84(lat, lon) or validate_radius_m(radius_m, max_m=_MAX_RADIUS_M)
    if err is not None:
        return err
    if not isinstance(months, int) or not 1 <= months <= _MAX_MONTHS:
        return {"error": "invalid_months", "message": f"months must be 1..{_MAX_MONTHS}."}

    pool = await get_pool()
    # Statement timeout bounds the worst-case cost of a big-radius-+-
    # long-window combo against a dense urban centre. A 5 km radius over
    # 36 months at Westminster can scan hundreds of thousands of rows;
    # anything taking more than 15 s is either data drift or an abuser,
    # and asyncpg will cancel cleanly and surface an error to the caller
    # rather than hogging the pool.
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH pt AS (
                    SELECT ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 27700) AS g
                ),
                win AS (
                    SELECT COALESCE(MAX(month), CURRENT_DATE) AS latest FROM staging.police_crimes
                )
                SELECT crime_type, month::text AS month, COUNT(*)::int AS n
                  FROM staging.police_crimes p, pt, win
                 WHERE ST_DWithin(p.geom_osgb, pt.g, $3)
                   AND p.month >= (win.latest - make_interval(months => $4))::date
                 GROUP BY crime_type, month
                 ORDER BY month, crime_type
                """,
                lon, lat, radius_m, months,
                timeout=15.0,
            )
    except asyncio.TimeoutError:
        return {
            "error": "query_timeout",
            "message": (
                "The crime query took too long to complete — try a "
                "smaller radius or shorter time window."
            ),
        }

    total = sum(r["n"] for r in rows)
    by_type: dict[str, int] = {}
    by_month: dict[str, int] = {}
    for r in rows:
        by_type[r["crime_type"]] = by_type.get(r["crime_type"], 0) + r["n"]
        # Keep "YYYY-MM" for display (source month string is "YYYY-MM-01").
        m = r["month"][:7]
        by_month[m] = by_month.get(m, 0) + r["n"]

    coverage_note = None
    if total == 0:
        # Scotland falls outside coverage; a Scottish point will return 0.
        # We detect "probably Scotland" via the NI bbox (rough) only to
        # emit a useful hint — English/Welsh points returning 0 are
        # genuinely quiet, so don't falsely flag them.
        if lat >= 54.6:  # very roughly north of the England-Scotland border
            coverage_note = (
                "No crimes found. If this point is in Scotland, "
                "data.police.uk does not carry Police Scotland data — "
                "use Police Scotland Recorded Crime statistics instead."
            )

    return {
        "center": {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "radius_m": radius_m,
            "months_window": months,
        },
        "count": total,
        "by_crime_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
        "by_month": [{"month": m, "count": n} for m, n in sorted(by_month.items())],
        "coverage_note": coverage_note,
        "source": "data.police.uk",
        "attribution": _ATTRIBUTION,
    }
