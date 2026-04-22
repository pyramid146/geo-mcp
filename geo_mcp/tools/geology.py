from __future__ import annotations

from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._validators import validate_wgs84

_ATTRIBUTION = (
    "Contains BGS © UKRI. Licensed under the Open Government Licence v3.0. "
    "Geology data is DiGMapGB-625 (BGS Geology 625k) — 1:625,000 scale, "
    "regional interpretation only; not suitable for property-specific foundation decisions."
)


async def geology_uk(lat: float, lon: float) -> dict[str, Any]:
    """Return BGS Geology 625k bedrock and superficial deposits at a WGS84 point.

    Two layers are consulted:

    * **Bedrock** — the underlying solid-rock formation. Always present
      somewhere under any UK point. Tells you whether the area is built
      on clay, chalk, limestone, sandstone, granite, etc.
    * **Superficial deposits** — younger unconsolidated material sitting
      on top of the bedrock (alluvium along river valleys, glacial till
      across large parts of northern Britain, made ground in cities,
      peat in upland areas). Often absent — the tool returns null for
      the superficial block on exposed-bedrock terrain.

    Typical property-risk uses:
      - "What's this house built on?" — superficial deposit (if any) is
        what matters for foundations and surface drainage; bedrock
        matters for deeper geotechnics and contaminant transport.
      - Shrink-swell clay bedrock (London Clay, Oxford Clay, Lias
        Group) pairs with subsidence risk.
      - Alluvium + peat superficial pair with historic flood risk.
      - Chalk / limestone bedrock pairs with karst / dissolution risk.

    Scale caveat: 1:625,000 is a national-scale interpretation. At a
    specific property, the BGS own advice is that this data is "not
    suitable for property-specific foundation decisions" — the response
    carries that language in the ``attribution`` string. For a proper
    site assessment a surveyor would commission a BGS Site Report
    (commercial product) or look at BGS Geology 50k (also commercial).

    Coverage is **Great Britain and Northern Ireland** (one of the few
    datasets here with NI coverage).

    Arguments:
        lat: WGS84 latitude, -90..90.
        lon: WGS84 longitude, -180..180.

    Returns:
        {
          "bedrock": {
              "formation_name": str | null,   # e.g. "London Clay Formation"
              "rock_type": str | null,        # e.g. "MUDSTONE"
              "group": str | null,            # higher-level stratigraphic group
              "age_oldest": str | null,       # e.g. "EOCENE"
              "age_youngest": str | null
          } | null,
          "superficial": {
              "deposit_name": str | null,     # e.g. "ALLUVIUM"
              "rock_type": str | null,
              "group": str | null,
              "age_oldest": str | null,
              "age_youngest": str | null
          } | null,
          "source": "BGS Geology 625k (DiGMapGB-625)",
          "scale": "1:625,000",
          "attribution": "..."
        }

    On invalid lat/lon, returns ``{"error": ..., "message": ...}``.
    """
    err = validate_wgs84(lat, lon)
    if err is not None:
        return err

    pool = await get_pool()
    async with pool.acquire() as conn:
        bedrock = await conn.fetchrow(
            """
            WITH pt AS (SELECT ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 27700) AS g)
            SELECT lex_d, rcs_d, gp_eq_d, max_time_d, min_time_d
              FROM staging.bgs_bedrock b, pt
             WHERE ST_Covers(b.geom, pt.g)
             LIMIT 1
            """,
            lon, lat,
        )
        superficial = await conn.fetchrow(
            """
            WITH pt AS (SELECT ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 27700) AS g)
            SELECT lex_d, rcs_d, supgp_eq_d, max_age, min_age
              FROM staging.bgs_superficial s, pt
             WHERE ST_Covers(s.geom, pt.g)
             LIMIT 1
            """,
            lon, lat,
        )

    return {
        "bedrock": _bedrock_block(bedrock) if bedrock else None,
        "superficial": _superficial_block(superficial) if superficial else None,
        "source": "BGS Geology 625k (DiGMapGB-625)",
        "scale": "1:625,000",
        "attribution": _ATTRIBUTION,
    }


def _bedrock_block(row) -> dict[str, Any]:
    return {
        "formation_name": row["lex_d"],
        "rock_type":      row["rcs_d"],
        "group":          row["gp_eq_d"] if row["gp_eq_d"] and row["gp_eq_d"] != "No Parent" else None,
        "age_oldest":     row["max_time_d"],
        "age_youngest":   row["min_time_d"],
    }


def _superficial_block(row) -> dict[str, Any]:
    return {
        "deposit_name": row["lex_d"],
        "rock_type":    row["rcs_d"] or None,
        "group":        row["supgp_eq_d"] or None,
        "age_oldest":   row["max_age"],
        "age_youngest": row["min_age"],
    }
