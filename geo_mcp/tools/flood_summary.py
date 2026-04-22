from __future__ import annotations

from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._area import resolve_area

_ATTRIBUTION = (
    "Contains Environment Agency data © Environment Agency copyright and/or "
    "database right 2025 and ONS Postcode Directory data. Licensed under the "
    "Open Government Licence v3.0."
)

# Count target postcodes up-front so we can reject runaway LAD/region
# queries fast instead of waiting for a timeout.
_COUNT_TEMPLATE = """
SELECT COUNT(*)::int
  FROM staging.onspd
 WHERE {area_filter} AND doterm IS NULL AND geom_osgb IS NOT NULL;
"""

# RoFRS aggregation over the target postcodes. A CTE first materialises
# the target pcds list (so the area filter's raw `pcds` reference isn't
# ambiguous against rofrs_postcodes.pcds), then joins RoFRS. Postcodes
# without a RoFRS entry naturally drop out.
_ROFRS_TEMPLATE = """
WITH target_pcds AS (
    SELECT pcds FROM staging.onspd
     WHERE {area_filter} AND doterm IS NULL
)
SELECT
    COUNT(*)                                         ::int AS postcodes_with_rofrs_entry,
    COUNT(*) FILTER (WHERE r.res_cnt_high > 0)       ::int AS postcodes_with_residential_high,
    COUNT(*) FILTER (WHERE r.res_cnt_medium > 0
                       OR r.res_cnt_high > 0)        ::int AS postcodes_with_residential_medium_plus,
    COALESCE(SUM(r.res_cnt_high),    0)::int AS residential_high,
    COALESCE(SUM(r.res_cnt_medium),  0)::int AS residential_medium,
    COALESCE(SUM(r.res_cnt_low),     0)::int AS residential_low,
    COALESCE(SUM(r.res_cnt_verylow), 0)::int AS residential_very_low,
    COALESCE(SUM(r.res_cntpc),       0)::int AS total_residential_properties_in_at_risk_postcodes
  FROM target_pcds t
  JOIN staging.rofrs_postcodes r ON r.pcds = t.pcds;
"""

# Reads the precomputed geom_osgb column (migration 002), so no per-row
# reprojection. EXISTS probes FZ3 first, then FZ2; short-circuits on the
# first polygon hit.
_QUERY_TEMPLATE = """
SELECT
    CASE
      WHEN EXISTS (
          SELECT 1 FROM staging.ea_flood_zones z
           WHERE z.flood_zone = 'FZ3' AND ST_Intersects(z.geom, o.geom_osgb)
      ) THEN 'FZ3'
      WHEN EXISTS (
          SELECT 1 FROM staging.ea_flood_zones z
           WHERE z.flood_zone = 'FZ2' AND ST_Intersects(z.geom, o.geom_osgb)
      ) THEN 'FZ2'
      ELSE 'FZ1'
    END AS zone,
    COUNT(*)::int AS n
  FROM staging.onspd o
 WHERE {area_filter} AND o.doterm IS NULL AND o.geom_osgb IS NOT NULL
 GROUP BY 1;
"""

# Cap chosen so the tool call stays under ~15s on current hardware. Per-
# postcode cost is ~2–3 ms (reproject-free GIST probe + ST_Intersects
# against EA polygons). Precomputing `flood_zone` on ONSPD in a future
# phase would lift this to arbitrary LAD / regional scope.
_MAX_POSTCODES = 5_000
_SUMMARY_TIMEOUT_S = 15.0


async def flood_risk_summary_uk(area: str) -> dict[str, Any]:
    """Aggregate EA Flood Zone coverage across every live postcode in a UK area.

    Use this when the caller asks a population-scale flood question —
    "what's the flood risk in Trowbridge?", "how exposed is Wiltshire?",
    "what share of BA14 sits in flood zone 3?". For a single point, use
    ``flood_risk_uk`` instead.

    The ``area`` argument accepts four forms, tried in order:
      1. **Postcode district** — ``"BA14"``, ``"M2"``, ``"SW1A"``.
      2. **GSS local-authority code** — ``"E06000054"`` (Wiltshire),
         ``"S12000005"``, etc.
      3. **Local-authority name** — ``"Wiltshire"``, ``"Manchester"``,
         ``"City of Westminster"``. Case-insensitive.
      4. **Populated-place name** — ``"Trowbridge"``, ``"Bath"``.
         Resolved via OS OpenNames to the place's postcode district
         (useful heuristic but inexact — a place can straddle districts).

    Coverage is **England only** (the dataset). Welsh, Scottish, and
    Northern Irish postcodes are counted but will all land in zone 1
    because no polygon covers them — check the country before trusting
    a "looks clean" summary for those areas.

    **Scale limit:** this tool caps at 5,000 live postcodes per call —
    enough for any postcode district and for small to mid-sized towns,
    but smaller than a typical local authority. For an LAD-scale query
    ("Wiltshire", "Manchester LAD"), the tool returns an
    ``area_too_large`` error; the caller should narrow to one or more
    postcode districts instead.

    Arguments:
        area: one of the four forms above.

    Two complementary signals sit in the response:
      * ``by_zone`` — planning-grade zones from the EA Flood Map for Planning
        (ignores flood defences). Good for "is any of this area under
        planning constraints".
      * ``probability`` — insurance-grade counts from RoFRS (accounts for
        defences). Good for "how many homes in this area are actually at
        risk of flooding in practice". ``null`` if no RoFRS-listed
        postcodes fall in the area.

    Returns:
        {
          "area": {"input", "method", "resolved_to"},
          "postcodes_considered": int,
          "by_zone": {"1": int, "2": int, "3": int},
          "worst_zone": 1 | 2 | 3,
          "pct_in_any_flood_zone": float,          # zones 2 + 3 as % of total
          "probability": {
              "postcodes_with_rofrs_entry": int,
              "postcodes_with_residential_high": int,
              "postcodes_with_residential_medium_plus": int,
              "residential_properties_by_band": {"high","medium","low","very_low"},
              "total_residential_properties_in_at_risk_postcodes": int
          } | null,
          "coverage_note": "...",
          "source": "...",
          "attribution": "..."
        }

    On an area that resolves to zero postcodes or can't be matched,
    returns ``{"error": ..., "message": ...}``.
    """
    if not isinstance(area, str) or not area.strip():
        return {"error": "invalid_input", "message": "area must be a non-empty string."}

    pool = await get_pool()
    async with pool.acquire() as conn:
        resolved = await resolve_area(area, conn)
        if resolved is None:
            return {
                "error": "unresolved_area",
                "message": (
                    f"Could not resolve {area!r} as a postcode district, GSS code, "
                    "local-authority name, or known populated place."
                ),
            }
        count_sql = _COUNT_TEMPLATE.format(area_filter=resolved.filter_sql)
        n = await conn.fetchval(count_sql, resolved.param)
        if n is None or n == 0:
            return {
                "error": "empty_area",
                "message": (
                    f"{area!r} resolved to {resolved.resolved_to} but no live "
                    "postcodes were found there."
                ),
                "area": resolved.to_meta(area),
            }
        if n > _MAX_POSTCODES:
            return {
                "error": "area_too_large",
                "message": (
                    f"{resolved.resolved_to} contains {n} live postcodes; the "
                    f"summary tool caps at {_MAX_POSTCODES}. Narrow the area "
                    "(e.g. use a postcode district instead of a whole LAD or region)."
                ),
                "area": resolved.to_meta(area),
                "postcodes_considered": n,
            }

        sql = _QUERY_TEMPLATE.format(area_filter=resolved.filter_sql)
        rows = await conn.fetch(sql, resolved.param, timeout=_SUMMARY_TIMEOUT_S)

        rofrs_sql = _ROFRS_TEMPLATE.format(area_filter=resolved.filter_sql)
        rofrs_row = await conn.fetchrow(rofrs_sql, resolved.param)

    by_zone = {"1": 0, "2": 0, "3": 0}
    for r in rows:
        key = r["zone"].removeprefix("FZ")
        by_zone[key] = r["n"]
    total = sum(by_zone.values())

    worst = 3 if by_zone["3"] else (2 if by_zone["2"] else 1)
    flood_exposed = by_zone["2"] + by_zone["3"]

    probability: dict[str, Any] | None = None
    if rofrs_row is not None and rofrs_row["postcodes_with_rofrs_entry"] > 0:
        probability = {
            "postcodes_with_rofrs_entry":              rofrs_row["postcodes_with_rofrs_entry"],
            "postcodes_with_residential_high":         rofrs_row["postcodes_with_residential_high"],
            "postcodes_with_residential_medium_plus":  rofrs_row["postcodes_with_residential_medium_plus"],
            "residential_properties_by_band": {
                "high":     rofrs_row["residential_high"],
                "medium":   rofrs_row["residential_medium"],
                "low":      rofrs_row["residential_low"],
                "very_low": rofrs_row["residential_very_low"],
            },
            "total_residential_properties_in_at_risk_postcodes":
                rofrs_row["total_residential_properties_in_at_risk_postcodes"],
        }

    return {
        "area": resolved.to_meta(area),
        "postcodes_considered": total,
        "by_zone": by_zone,
        "worst_zone": worst,
        "pct_in_any_flood_zone": round(100 * flood_exposed / total, 2),
        "probability": probability,
        "coverage_note": (
            "`by_zone` is from the EA Flood Map for Planning — England only; "
            "postcodes outside England land in zone 1 by default. "
            "`probability` is from EA RoFRS (England only too) and accounts "
            "for flood defences; postcodes not in RoFRS simply aren't counted "
            "there rather than being treated as zero-risk."
        ),
        "source": (
            "ONSPD Feb 2026 + EA Flood Map for Planning + EA RoFRS (Postcodes in Areas at Risk)"
        ),
        "attribution": _ATTRIBUTION,
    }
