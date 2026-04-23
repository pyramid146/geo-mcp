"""Roads lookup — OS Open Roads."""
from __future__ import annotations

from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._validators import validate_radius_m, validate_wgs84

_ATTRIBUTION = (
    "Contains OS data © Crown copyright and database right 2026. OS Open "
    "Roads is licensed under the Open Government Licence v3.0."
)

_DEFAULT_RADIUS_M = 500
_MAX_RADIUS_M = 10_000

_VALID_CLASSES = frozenset({
    "Motorway", "A Road", "B Road",
    "Classified Unnumbered", "Unclassified",
    "Not Classified", "Unknown",
})

# For nearest-major-road shortcuts; sort descending importance.
_MAJOR_CLASS_ORDER = ["Motorway", "A Road", "B Road"]


async def road_nearby_uk(
    lat: float,
    lon: float,
    radius_m: int = _DEFAULT_RADIUS_M,
    classes: list[str] | None = None,
) -> dict[str, Any]:
    """Roads within a radius of a UK point, with classification.

    Backed by OS Open Roads (~4 M road-link segments across GB). Each
    segment is tagged with class (Motorway, A Road, B Road, Classified
    Unnumbered, Unclassified) plus road number / name where known.

    Useful for "how close is this property to a motorway or A-road?"
    (noise / access), "what's the nearest named street?" (address
    sanity check), or "road-class mix of the area" (quality-of-life
    context).

    Coverage: Great Britain.

    Arguments:
        lat, lon: WGS84.
        radius_m: 1–10 000 m, default 500.
        classes: optional filter list (e.g. ``["Motorway", "A Road"]``
            to find only major roads).

    Returns:
        {
          "center": {"lat", "lon", "radius_m"},
          "nearest_major": {"class", "road_number", "name", "distance_m"} | null,
          "nearest_by_class": {"Motorway": {...} | null, "A Road": {...}, ...},
          "roads": [...up to 15 unique (road_number, name) pairs, nearest first...],
          "source": "OS Open Roads",
          "attribution": "..."
        }

    ``nearest_major`` is the nearest road classified Motorway / A Road /
    B Road in that order. If no major road is within the radius, it's
    null. ``nearest_by_class`` gives the nearest in each of those
    three classes individually.
    """
    err = validate_wgs84(lat, lon) or validate_radius_m(radius_m, max_m=_MAX_RADIUS_M)
    if err is not None:
        return err

    filter_classes: list[str] | None = None
    if classes is not None:
        if not isinstance(classes, list) or not all(isinstance(c, str) for c in classes):
            return {"error": "invalid_classes", "message": "classes must be a list of strings."}
        bad = [c for c in classes if c not in _VALID_CLASSES]
        if bad:
            return {
                "error": "invalid_classes",
                "message": f"Unknown classes: {bad!r}. Valid: {sorted(_VALID_CLASSES)}.",
            }
        filter_classes = classes

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH pt AS (
                SELECT ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 27700) AS g
            ), hits AS (
                SELECT DISTINCT ON (COALESCE(roadnumber, ''), COALESCE(name1, ''))
                       class, roadnumber, name1,
                       ST_Distance(r.geom_osgb, pt.g)::float8 AS distance_m
                  FROM staging.os_roads r, pt
                 WHERE ST_DWithin(r.geom_osgb, pt.g, $3)
                   AND ($4::text[] IS NULL OR r.class = ANY($4))
                 ORDER BY COALESCE(roadnumber, ''), COALESCE(name1, ''),
                          ST_Distance(r.geom_osgb, pt.g)
            )
            SELECT * FROM hits ORDER BY distance_m LIMIT 15
            """,
            lon, lat, radius_m, filter_classes,
        )

    roads = [
        {
            "class": r["class"],
            "road_number": r["roadnumber"] or None,
            "name": r["name1"] or None,
            "distance_m": round(float(r["distance_m"]), 1),
        }
        for r in rows
    ]

    nearest_by_class: dict[str, dict | None] = {c: None for c in _MAJOR_CLASS_ORDER}
    for road in roads:
        cls = road["class"]
        if cls in nearest_by_class and nearest_by_class[cls] is None:
            nearest_by_class[cls] = road

    nearest_major = None
    for cls in _MAJOR_CLASS_ORDER:
        if nearest_by_class[cls] is not None:
            nearest_major = nearest_by_class[cls]
            break

    return {
        "center": {"lat": round(lat, 6), "lon": round(lon, 6), "radius_m": radius_m},
        "nearest_major": nearest_major,
        "nearest_by_class": nearest_by_class,
        "roads": roads,
        "source": "OS Open Roads",
        "attribution": _ATTRIBUTION,
    }
