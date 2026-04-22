from __future__ import annotations

from typing import Any

import numpy as np

from geo_mcp.data_access.cog import open_cog
from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._area import resolve_area

_COG_NAME = "terrain50.tif"
_ATTRIBUTION = (
    "Contains OS data © Crown copyright and database right 2026 and ONS "
    "Postcode Directory data. Licensed under the Open Government Licence v3.0."
)

# Elevation sampling is cheap (a COG random-access read is sub-ms), so the
# cap here is higher than flood — 25k postcodes comfortably covers most
# LADs inside the 5 s tool budget.
_MAX_POSTCODES = 25_000

_COUNT_SQL = """
SELECT COUNT(*)::int
  FROM staging.onspd
 WHERE {area_filter} AND doterm IS NULL AND geom_osgb IS NOT NULL;
"""

_FETCH_SQL = """
SELECT pcds,
       ST_X(geom_osgb)::float8 AS east,
       ST_Y(geom_osgb)::float8 AS north
  FROM staging.onspd
 WHERE {area_filter} AND doterm IS NULL AND geom_osgb IS NOT NULL;
"""


async def elevation_summary_uk(area: str) -> dict[str, Any]:
    """Summarise OS Terrain 50 elevations across all live postcodes in a UK area.

    Use this when the caller asks a population-scale elevation question —
    "how hilly is Sheffield?", "average elevation in Plymouth", "how much
    of PL1 is below 10 m?". For a single point, use ``elevation`` instead.

    The ``area`` argument accepts the same four forms as
    ``flood_risk_summary_uk``:
      1. Postcode district — ``"PL1"``, ``"M2"``, ``"SW1A"``.
      2. GSS local-authority code — ``"E06000054"``, ``"S12000005"``.
      3. Local-authority name — ``"Wiltshire"``, ``"Manchester"``.
      4. Populated-place name — ``"Trowbridge"``, ``"Bath"`` — resolved
         via OS OpenNames to that place's postcode district.

    Each postcode's centroid is sampled against the 50 m digital terrain
    model. Postcodes outside GB (Northern Ireland, Crown Dependencies) or
    on the small NR33 data gap return no reading and are reported under
    ``out_of_coverage``; stats are computed over the valid samples only.

    **Scale limit:** up to 25,000 postcodes per call (covers almost all
    UK local authorities). Bigger areas return an ``area_too_large`` error.

    Arguments:
        area: one of the four forms above.

    Returns:
        {
          "area": {"input", "method", "resolved_to"},
          "postcodes_considered": int,
          "valid_samples": int,
          "out_of_coverage": int,
          "elevation_m": {
              "mean": float, "min": float, "max": float,
              "p10": float, "median": float, "p90": float
          },
          "source": "OS Terrain 50 (50 m DTM)",
          "datum": "OSGB36 vertical (~mean sea level)",
          "attribution": "..."
        }

    Error shape on bad input:
        {"error": ..., "message": ..., ...}
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
        count = await conn.fetchval(_COUNT_SQL.format(area_filter=resolved.filter_sql), resolved.param)
        if not count:
            return {
                "error": "empty_area",
                "message": f"{area!r} resolved to {resolved.resolved_to} but no live postcodes were found there.",
                "area": resolved.to_meta(area),
            }
        if count > _MAX_POSTCODES:
            return {
                "error": "area_too_large",
                "message": (
                    f"{resolved.resolved_to} contains {count} live postcodes; "
                    f"the elevation summary tool caps at {_MAX_POSTCODES}. "
                    "Narrow the area (e.g. a postcode district or a single town)."
                ),
                "area": resolved.to_meta(area),
                "postcodes_considered": count,
            }
        rows = await conn.fetch(_FETCH_SQL.format(area_filter=resolved.filter_sql), resolved.param)

    ds = open_cog(_COG_NAME)
    nodata = ds.nodata
    left, bottom, right, top = ds.bounds

    eastings = [r["east"] for r in rows]
    northings = [r["north"] for r in rows]
    samples = ds.sample(list(zip(eastings, northings, strict=True)), indexes=1)

    values: list[float] = []
    out_of_cov = 0
    for e, n, s in zip(eastings, northings, samples, strict=True):
        if not (left <= e <= right and bottom <= n <= top):
            out_of_cov += 1
            continue
        v = float(s[0])
        if nodata is not None and v == nodata:
            out_of_cov += 1
            continue
        values.append(v)

    if not values:
        return {
            "error": "no_valid_samples",
            "message": (
                f"None of the {count} postcodes in {resolved.resolved_to} fall inside "
                "OS Terrain 50's coverage (GB-only)."
            ),
            "area": resolved.to_meta(area),
            "postcodes_considered": count,
            "out_of_coverage": out_of_cov,
        }

    arr = np.asarray(values, dtype=np.float64)
    return {
        "area": resolved.to_meta(area),
        "postcodes_considered": count,
        "valid_samples": int(arr.size),
        "out_of_coverage": out_of_cov,
        "elevation_m": {
            "mean":   round(float(arr.mean()), 2),
            "min":    round(float(arr.min()), 2),
            "max":    round(float(arr.max()), 2),
            "p10":    round(float(np.percentile(arr, 10)), 2),
            "median": round(float(np.percentile(arr, 50)), 2),
            "p90":    round(float(np.percentile(arr, 90)), 2),
        },
        "source": "OS Terrain 50 (50 m DTM)",
        "datum": "OSGB36 vertical (~mean sea level)",
        "attribution": _ATTRIBUTION,
    }
