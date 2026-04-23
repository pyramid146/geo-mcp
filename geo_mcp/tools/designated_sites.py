"""Natural England statutory designated sites + Ancient Woodland.

Covers the eight designation types that drive planning + environmental
decisions for a UK point:

  * **SSSI** — Sites of Special Scientific Interest (biological/geological)
  * **SAC**  — Special Areas of Conservation (EU Habitats Directive)
  * **SPA**  — Special Protection Areas (EU Birds Directive)
  * **Ramsar** — wetlands of international importance
  * **NNR**  — National Nature Reserves
  * **LNR**  — Local Nature Reserves
  * **AONB** — Areas of Outstanding Natural Beauty (now "National Landscapes")
  * **AncientWoodland** — continuously-wooded since at least 1600

Coverage is **England only** (Natural England is the source body;
Scotland, Wales, and NI have equivalent NatureScot / NRW / DAERA
designations that aren't in this dataset).
"""
from __future__ import annotations

from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._validators import validate_radius_m, validate_wgs84

_ATTRIBUTION = (
    "Contains Natural England data © Natural England, licensed under the "
    "Open Government Licence v3.0. Sources: Sites of Special Scientific "
    "Interest (SSSI), Special Areas of Conservation (SAC), Special "
    "Protection Areas (SPA), Ramsar Sites, National Nature Reserves (NNR), "
    "Local Nature Reserves (LNR), Areas of Outstanding Natural Beauty / "
    "National Landscapes (AONB), Ancient Woodland Inventory."
)

_VALID_TYPES = frozenset({
    "SSSI", "SAC", "SPA", "Ramsar", "NNR", "LNR", "AONB", "AncientWoodland",
})

_DEFAULT_RADIUS_M = 500
_MAX_RADIUS_M = 5_000
_MAX_RESULTS = 25


async def designated_sites_nearby_uk(
    lat: float,
    lon: float,
    radius_m: int = _DEFAULT_RADIUS_M,
    types: list[str] | None = None,
) -> dict[str, Any]:
    """Statutory environmental / landscape designations within a radius.

    Answers questions like "is this property inside a SSSI?", "what
    protected habitats are within 500 m?", "is this in an AONB?" — the
    planning-constraint questions a surveyor, conveyancer, or
    environmental consultant is paid to check.

    Uses PostGIS distance (metres in OSGB). `distance_m = 0` means the
    point is **inside** the designation polygon.

    Arguments:
        lat, lon: WGS84.
        radius_m: 1–5000 m, default 500.
        types: optional filter list from the set
            ``{SSSI, SAC, SPA, Ramsar, NNR, LNR, AONB, AncientWoodland}``.
            Omit for all types.

    Returns:
        {
          "center": {"lat", "lon", "radius_m"},
          "count_by_type": {"SSSI": 1, "AncientWoodland": 3, ...},
          "total": int,
          "designations": [  // up to 25, nearest first
              {"designation_type", "name", "code", "distance_m"},
              ...
          ],
          "in_any_designation": bool,   // true if any distance_m == 0
          "coverage_note": "England only; NE sources",
          "source": "Natural England",
          "attribution": "..."
        }
    """
    err = validate_wgs84(lat, lon) or validate_radius_m(radius_m, max_m=_MAX_RADIUS_M)
    if err is not None:
        return err

    filter_types: list[str] | None = None
    if types is not None:
        if not isinstance(types, list) or not all(isinstance(t, str) for t in types):
            return {"error": "invalid_types", "message": "types must be a list of strings."}
        bad = [t for t in types if t not in _VALID_TYPES]
        if bad:
            return {
                "error": "invalid_types",
                "message": (
                    f"Unknown designation types: {bad!r}. "
                    f"Valid values: {sorted(_VALID_TYPES)}."
                ),
            }
        filter_types = types

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH pt AS (
                SELECT ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 27700) AS g
            )
            SELECT designation_type, name, code,
                   ST_Distance(d.geom_osgb, pt.g)::float8 AS distance_m
              FROM staging.ne_designated_sites d, pt
             WHERE ST_DWithin(d.geom_osgb, pt.g, $3)
               AND ($4::text[] IS NULL OR d.designation_type = ANY($4))
             ORDER BY ST_Distance(d.geom_osgb, pt.g)
             LIMIT $5
            """,
            lon, lat, radius_m, filter_types, _MAX_RESULTS,
        )

    designations = [
        {
            "designation_type": r["designation_type"],
            "name": r["name"],
            "code": r["code"],
            "distance_m": round(float(r["distance_m"]), 1),
        }
        for r in rows
    ]

    count_by_type: dict[str, int] = {}
    for d in designations:
        count_by_type[d["designation_type"]] = count_by_type.get(d["designation_type"], 0) + 1

    return {
        "center": {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "radius_m": radius_m,
        },
        "count_by_type": count_by_type,
        "total": len(designations),
        "designations": designations,
        "in_any_designation": any(d["distance_m"] == 0 for d in designations),
        "coverage_note": (
            "England only. For Scottish, Welsh, or NI designations use "
            "NatureScot SiteLink, NRW Lle, or DAERA respectively."
        ),
        "source": "Natural England",
        "attribution": _ATTRIBUTION,
    }
