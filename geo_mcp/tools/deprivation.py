"""Index of Multiple Deprivation lookup for a UK postcode / point."""
from __future__ import annotations

from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._validators import (
    canonical_spaced_postcode,
    is_valid_uk_postcode,
    validate_wgs84,
)

_ATTRIBUTION = (
    "Contains English Indices of Deprivation 2019 data © Crown copyright 2019, "
    "licensed under the Open Government Licence v3.0. Published by the "
    "Ministry of Housing, Communities & Local Government (now MHCLG). "
    "IMD 2019 is the most recent published release; deprivation picture "
    "may have shifted since the 2015/16 underlying data was collected."
)


def _decile_label(d: int) -> str:
    # IoD convention: decile 1 = most deprived 10%, decile 10 = least deprived.
    ordinals = {
        1:  "most deprived 10%",
        2:  "2nd most deprived 10%",
        3:  "3rd most deprived 10%",
        4:  "4th most deprived 10%",
        5:  "5th most deprived 10%",
        6:  "6th most deprived 10% (mid-scale)",
        7:  "4th least deprived 10%",
        8:  "3rd least deprived 10%",
        9:  "2nd least deprived 10%",
        10: "least deprived 10%",
    }
    return ordinals.get(d, "unknown")


async def deprivation_uk(
    postcode: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> dict[str, Any]:
    """English Indices of Deprivation (IoD 2019) decile + rank for a point.

    Accepts **either** a postcode **or** a WGS84 lat/lon. Resolves the
    location to its LSOA (2011) via ONSPD, then joins the MHCLG IMD 2019
    table to return the Index of Multiple Deprivation decile (1 =
    most deprived, 10 = least deprived) and rank (1 of 32,844).

    IMD combines seven weighted domains: Income, Employment, Education,
    Health, Crime, Barriers to Housing & Services, Living Environment.
    The headline decile is what planning reports, insurance underwriting
    models, and property-risk tools typically cite.

    Coverage: **England only** — the IoD is separately published by
    Wales, Scotland and NI and isn't combined into this table.

    Arguments (provide exactly one of):
        postcode: UK postcode, spaced or unspaced.
        lat, lon: WGS84 coordinates.

    Returns:
        {
          "postcode": "SW1A 1AA",
          "lsoa": {"code", "name"},
          "lad":  {"code", "name"},
          "imd_decile": 8,
          "imd_rank": 25478,
          "decile_label": "3rd least deprived 10%",
          "source": "IMD 2019 (MHCLG)",
          "attribution": "..."
        }

    On invalid input returns ``{"error": ..., "message": ...}``.
    On coords that resolve outside England (Scotland, Wales, NI) returns
    ``{"coverage_gap": true, ...}`` — still structured, still agent-readable.
    """
    have_pc = bool(postcode and postcode.strip())
    have_coord = (lat is not None) and (lon is not None)
    if have_pc == have_coord:
        return {"error": "invalid_input", "message": "Provide exactly one of: postcode, or both lat and lon."}

    if have_coord:
        err = validate_wgs84(lat, lon)
        if err is not None:
            return err

    pool = await get_pool()
    async with pool.acquire() as conn:
        if have_pc:
            q = (postcode or "").strip().upper()
            if not is_valid_uk_postcode(q):
                return {"error": "invalid_postcode", "message": f"{postcode!r} is not a UK postcode."}
            spaced = canonical_spaced_postcode(q)
            row = await conn.fetchrow(
                """
                SELECT o.pcds AS postcode, o.lsoa11cd, o.lad25cd,
                       i.lsoa11_name, i.lad19_name, i.imd_rank, i.imd_decile
                  FROM staging.onspd o
                  LEFT JOIN staging.imd_2019 i ON i.lsoa11_code = o.lsoa11cd
                 WHERE o.pcds = $1 AND o.doterm IS NULL
                 LIMIT 1
                """,
                spaced,
            )
        else:
            row = await conn.fetchrow(
                """
                WITH nearest AS (
                    SELECT pcds, lsoa11cd, lad25cd
                      FROM staging.onspd
                     WHERE geom IS NOT NULL AND doterm IS NULL
                     ORDER BY geom <-> ST_SetSRID(ST_MakePoint($1, $2), 4326)
                     LIMIT 1
                )
                SELECT n.pcds AS postcode, n.lsoa11cd, n.lad25cd,
                       i.lsoa11_name, i.lad19_name, i.imd_rank, i.imd_decile
                  FROM nearest n
                  LEFT JOIN staging.imd_2019 i ON i.lsoa11_code = n.lsoa11cd
                """,
                lon, lat,
            )

    if row is None:
        return {"error": "not_found", "message": "Postcode not in ONSPD."}

    if row["imd_decile"] is None:
        # LSOA not in IoD 2019 = point is outside England.
        return {
            "coverage_gap": True,
            "postcode": row["postcode"],
            "lsoa": {"code": row["lsoa11cd"], "name": None},
            "message": (
                "LSOA is outside England — IoD 2019 only covers England. "
                "For Wales use the Welsh Index of Multiple Deprivation (WIMD); "
                "Scotland uses SIMD; NI uses NIMDM."
            ),
            "source": "IMD 2019 (MHCLG)",
            "attribution": _ATTRIBUTION,
        }

    return {
        "postcode": row["postcode"],
        "lsoa": {"code": row["lsoa11cd"], "name": row["lsoa11_name"]},
        "lad":  {"code": row["lad25cd"],  "name": row["lad19_name"]},
        "imd_decile": int(row["imd_decile"]),
        "imd_rank": int(row["imd_rank"]),
        "decile_label": _decile_label(int(row["imd_decile"])),
        "source": "IMD 2019 (MHCLG)",
        "attribution": _ATTRIBUTION,
    }
