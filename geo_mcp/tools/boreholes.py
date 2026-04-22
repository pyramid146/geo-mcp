from __future__ import annotations

import logging
from typing import Any

import httpx

from geo_mcp.data_access.projections import to_osgb
from geo_mcp.tools._validators import validate_radius_m, validate_wgs84

_BGS_ENDPOINT = (
    "https://map.bgs.ac.uk/arcgis/rest/services/GeoIndex_Onshore/boreholes/"
    "MapServer/0/query"
)
_DEFAULT_RADIUS_M = 500
_MAX_RADIUS_M = 5_000
_MAX_RECORDS_RETURNED = 25
_HTTP_TIMEOUT_S = 4.0

_ATTRIBUTION = (
    "Contains BGS © UKRI. Licensed under the Open Government Licence v3.0. "
    "Borehole locations are from the BGS GeoIndex Boreholes theme (live query)."
)

log = logging.getLogger(__name__)


async def boreholes_nearby_uk(
    lat: float,
    lon: float,
    radius_m: int = _DEFAULT_RADIUS_M,
) -> dict[str, Any]:
    """Find BGS-catalogued borehole records near a WGS84 point.

    Queries the BGS GeoIndex Boreholes layer (~1.36 M historical borehole
    records across Great Britain) live over the BGS ArcGIS REST endpoint
    and returns any that fall within the requested radius of the input
    point.

    Each borehole is a record of a drilled hole with a written or scanned
    log held by the BGS — drilled for construction, ground investigation,
    water supply, mineral exploration, or academic surveys. The scan URL
    (where present) links to the actual PDF log held in the BGS archive,
    which a surveyor can read to see what strata were encountered.

    The **count** of boreholes near a property is a useful proxy for how
    well-characterised the local ground is: a site with 20 recorded
    boreholes within 500 m has substantial existing investigation; one
    with zero may warrant a fresh ground investigation.

    Coverage is **Great Britain** (England, Scotland, Wales). Northern
    Ireland is not in GeoIndex Onshore.

    Arguments:
        lat: WGS84 latitude, -90..90.
        lon: WGS84 longitude, -180..180.
        radius_m: search radius in metres, default 500, capped at 5000.

    Returns:
        {
          "center": {"lat", "lon", "radius_m"},
          "count": int,                              # total within radius
          "nearest_m": float | null,                 # distance to closest
          "boreholes": [
              {"reference", "name", "grid_ref",
               "depth_m", "year", "held_at", "scan_url"},
              ...                                    # up to 25, nearest first
          ],
          "source": "BGS GeoIndex — Borehole.records",
          "attribution": "..."
        }

    On invalid input, returns ``{"error": ..., "message": ...}``. If the
    BGS endpoint is unreachable, returns
    ``{"error": "upstream_unavailable", "message": ...}`` rather than
    raising.
    """
    err = validate_wgs84(lat, lon) or validate_radius_m(radius_m, max_m=_MAX_RADIUS_M)
    if err is not None:
        return err

    east, north = to_osgb().transform(lon, lat)
    params = {
        "geometry": f"{east},{north}",
        "geometryType": "esriGeometryPoint",
        "distance": str(radius_m),
        "units": "esriSRUnit_Meter",
        "inSR": "27700",
        "outSR": "27700",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "REFERENCE,NAME,GRID_REF,EASTING,NORTHING,LENGTH,YEAR_KNOWN,HELD_AT,SCAN_URL",
        "returnGeometry": "true",
        "f": "json",
    }

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S) as client:
            resp = await client.get(_BGS_ENDPOINT, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        log.warning("BGS borehole query failed: %s", exc)
        return {
            "error": "upstream_unavailable",
            "message": f"BGS borehole endpoint could not be reached: {exc}",
            "center": {"lat": lat, "lon": lon, "radius_m": radius_m},
        }

    features = data.get("features", []) or []
    # Enrich each record with its distance from the input, then sort.
    enriched: list[tuple[float, dict[str, Any]]] = []
    for f in features:
        attrs = f.get("attributes", {}) or {}
        geom = f.get("geometry", {}) or {}
        fe, fn = geom.get("x"), geom.get("y")
        if fe is None or fn is None:
            continue
        dist = ((fe - east) ** 2 + (fn - north) ** 2) ** 0.5
        enriched.append((dist, _borehole_row(attrs, dist)))
    enriched.sort(key=lambda t: t[0])

    return {
        "center": {"lat": lat, "lon": lon, "radius_m": radius_m},
        "count": len(enriched),
        "nearest_m": round(enriched[0][0], 2) if enriched else None,
        "boreholes": [row for _, row in enriched[:_MAX_RECORDS_RETURNED]],
        "source": "BGS GeoIndex — Borehole.records",
        "attribution": _ATTRIBUTION,
    }


def _borehole_row(attrs: dict[str, Any], distance_m: float) -> dict[str, Any]:
    return {
        "reference": attrs.get("REFERENCE"),
        "name": attrs.get("NAME"),
        "grid_ref": attrs.get("GRID_REF"),
        "depth_m": _num_or_none(attrs.get("LENGTH")),
        "year": attrs.get("YEAR_KNOWN"),
        "held_at": attrs.get("HELD_AT"),
        "scan_url": attrs.get("SCAN_URL"),
        "distance_m": round(distance_m, 2),
    }


def _num_or_none(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None
