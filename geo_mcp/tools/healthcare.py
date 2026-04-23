"""GP-practice proximity lookup — NHS ODS epraccur + ebranchs."""
from __future__ import annotations

from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._validators import validate_radius_m, validate_wgs84

_ATTRIBUTION = (
    "Contains information from NHS Digital's Organisation Data Service "
    "(ODS), licensed under the Open Government Licence v3.0. GP practice "
    "lat/lon derived by joining the ODS postcode against ONSPD."
)

_DEFAULT_RADIUS_M = 2_000
_MAX_RADIUS_M = 20_000
_MAX_RESULTS = 25


async def gp_practices_nearby_uk(
    lat: float,
    lon: float,
    radius_m: int = _DEFAULT_RADIUS_M,
    active_only: bool = True,
) -> dict[str, Any]:
    """NHS GP practices and practice branches near a UK point.

    Backed by NHS Digital's ODS `epraccur` + `ebranchs` files: every
    prescribing GP practice and registered branch in England, Wales,
    Scotland and Northern Ireland. Geocoded by joining each practice's
    postcode against ONSPD.

    Useful for property workflows (healthcare access) and any "where
    are my local GPs?" query. Does NOT include hospitals, dentists,
    pharmacies, or private clinics — those are separate ODS files
    not currently ingested.

    Coverage: UK-wide.

    Arguments:
        lat, lon: WGS84.
        radius_m: 1–20 000 m, default 2 000.
        active_only: default True — exclude inactive / dormant
            practices + branches whose status is blank.

    Returns:
        {
          "center": {"lat", "lon", "radius_m"},
          "total": int,
          "practices": [
              {"org_code", "name", "postcode", "addr1", "town",
               "status", "distance_m"},
              ...up to 25 nearest
          ],
          "source": "NHS ODS (epraccur + ebranchs)",
          "attribution": "..."
        }
    """
    err = validate_wgs84(lat, lon) or validate_radius_m(radius_m, max_m=_MAX_RADIUS_M)
    if err is not None:
        return err

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH pt AS (
                SELECT ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 27700) AS g
            )
            SELECT org_code, name, postcode, addr1, town, status_code,
                   ST_Distance(p.geom_osgb, pt.g)::float8 AS distance_m
              FROM staging.nhs_gp_practices p, pt
             WHERE p.geom_osgb IS NOT NULL
               AND ST_DWithin(p.geom_osgb, pt.g, $3)
               AND (NOT $4 OR status_code = 'ACTIVE')
             ORDER BY ST_Distance(p.geom_osgb, pt.g)
             LIMIT $5
            """,
            lon, lat, radius_m, active_only, _MAX_RESULTS,
        )

    practices = [
        {
            "org_code": r["org_code"],
            "name": r["name"],
            "postcode": r["postcode"],
            "addr1": r["addr1"],
            "town": r["town"],
            "status": r["status_code"] or None,
            "distance_m": round(float(r["distance_m"]), 0),
        }
        for r in rows
    ]
    return {
        "center": {"lat": round(lat, 6), "lon": round(lon, 6), "radius_m": radius_m},
        "total": len(practices),
        "practices": practices,
        "source": "NHS ODS (epraccur + ebranchs)",
        "attribution": _ATTRIBUTION,
    }
