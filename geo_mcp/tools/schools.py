"""Schools lookup — Department for Education's GIAS register."""
from __future__ import annotations

from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._validators import validate_radius_m, validate_wgs84

_ATTRIBUTION = (
    "Contains information from the Department for Education's Get Information "
    "About Schools (GIAS) register, licensed under the Open Government Licence v3.0. "
    "Ofsted inspection outcomes © Ofsted."
)

_DEFAULT_RADIUS_M = 1_500
_MAX_RADIUS_M = 10_000
_MAX_RESULTS = 25

_VALID_PHASES = frozenset({
    "Primary", "Secondary", "All-through", "Nursery", "16 plus",
    "Middle deemed primary", "Middle deemed secondary", "Not applicable",
})


async def schools_nearby_uk(
    lat: float,
    lon: float,
    radius_m: int = _DEFAULT_RADIUS_M,
    phase: str | None = None,
    open_only: bool = True,
) -> dict[str, Any]:
    """Schools within a radius of a UK point, with Ofsted ratings.

    Backed by GIAS — the authoritative England-wide register of all
    schools: local authority maintained, academies, free schools,
    independent, special, PRUs, FE colleges. Every record carries the
    school's phase, age range, pupil count, Ofsted rating, and postcode.

    Coverage: England. Scotland / Wales / NI maintain separate registers
    (education is devolved) which are not in this dataset.

    Arguments:
        lat, lon: WGS84.
        radius_m: 1–10 000 m, default 1 500.
        phase: filter to one of {"Primary", "Secondary", "All-through",
            "Nursery", "16 plus", "Middle deemed primary",
            "Middle deemed secondary", "Not applicable"}.
        open_only: default True — exclude closed / proposed schools.

    Returns:
        {
          "center": {"lat", "lon", "radius_m"},
          "total": int,
          "count_by_phase":  {"Primary": 3, "Secondary": 1, ...},
          "count_by_ofsted": {"Outstanding": 1, "Good": 2, ...},
          "schools": [
              {"urn", "name", "phase", "type_group", "gender",
               "age_low", "age_high", "pupils", "capacity",
               "ofsted_rating", "ofsted_last_insp",
               "postcode", "town", "la_name",
               "distance_m"},
              ...up to 25 nearest
          ],
          "source": "DfE GIAS",
          "attribution": "..."
        }
    """
    err = validate_wgs84(lat, lon) or validate_radius_m(radius_m, max_m=_MAX_RADIUS_M)
    if err is not None:
        return err
    if phase is not None and phase not in _VALID_PHASES:
        return {
            "error": "invalid_phase",
            "message": f"phase must be one of {sorted(_VALID_PHASES)}.",
        }

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH pt AS (
                SELECT ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 27700) AS g
            )
            SELECT
                urn, name, phase, type_group, gender,
                age_low, age_high, pupils, capacity,
                ofsted_rating, ofsted_last_insp,
                postcode, town, la_name,
                ST_Distance(s.geom_osgb, pt.g)::float8 AS distance_m
              FROM staging.gias_schools s, pt
             WHERE s.geom_osgb IS NOT NULL
               AND ST_DWithin(s.geom_osgb, pt.g, $3)
               AND (NOT $4 OR s.status = 'Open')
               AND ($5::text IS NULL OR s.phase = $5)
             ORDER BY ST_Distance(s.geom_osgb, pt.g)
             LIMIT $6
            """,
            lon, lat, radius_m, open_only, phase, _MAX_RESULTS,
        )

    schools = [
        {
            "urn": r["urn"],
            "name": r["name"],
            "phase": r["phase"],
            "type_group": r["type_group"],
            "gender": r["gender"],
            "age_low": r["age_low"],
            "age_high": r["age_high"],
            "pupils": r["pupils"],
            "capacity": r["capacity"],
            "ofsted_rating": r["ofsted_rating"],
            "ofsted_last_insp": r["ofsted_last_insp"].isoformat() if r["ofsted_last_insp"] else None,
            "postcode": r["postcode"],
            "town": r["town"],
            "la_name": r["la_name"],
            "distance_m": round(float(r["distance_m"]), 0),
        }
        for r in rows
    ]
    by_phase: dict[str, int] = {}
    by_ofsted: dict[str, int] = {}
    for s in schools:
        if s["phase"]:
            by_phase[s["phase"]] = by_phase.get(s["phase"], 0) + 1
        if s["ofsted_rating"]:
            by_ofsted[s["ofsted_rating"]] = by_ofsted.get(s["ofsted_rating"], 0) + 1

    return {
        "center": {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "radius_m": radius_m,
        },
        "total": len(schools),
        "count_by_phase": by_phase,
        "count_by_ofsted": by_ofsted,
        "schools": schools,
        "coverage_note": (
            "England only. Scotland / Wales / NI maintain separate "
            "education-authority registers not included here."
        ),
        "source": "DfE GIAS",
        "attribution": _ATTRIBUTION,
    }
