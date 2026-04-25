"""BGS GeoIndex Offshore — sample, sediment, seismic, well discovery.

Companion to ``marine_data_exchange.py``. Where MDX holds the
developer-deposited survey datasets (offshore-wind era), BGS GeoIndex
Offshore holds the **public scientific record** for the UK Continental
Shelf — every BGS, government, university, and industry sample point
that's been deposited with the British Geological Survey since the
1960s. That's:

* Sediment / borehole / core / grab / drill samples (with PDF logs)
* Folk-classified seabed sediment (gravel / sand / mud %)
* 2D seismic reflection survey lines
* Hydrocarbon well headers (UK Continental Shelf wells, with status
  and original operator)

All four layers expose direct **scan URLs** to the BGS / NSTA archives,
so an agent can return downloadable PDFs / data packs alongside the
survey metadata.

Endpoint: ``map.bgs.ac.uk/arcgis/rest/services/GeoIndex_Offshore``
public ArcGIS REST, no auth, OGLv3.

Coverage: UK Continental Shelf — North Sea, English Channel, Western
Approaches, Celtic Sea, Irish Sea, West of Scotland, West of
Shetland. Onshore returns nothing.
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

import httpx

from geo_mcp.tools._validators import validate_radius_m, validate_wgs84

_BGS_BASE = (
    "https://map.bgs.ac.uk/arcgis/rest/services/"
    "GeoIndex_Offshore/offshore_data/MapServer"
)
_LAYER_SAMPLES = 3            # All Equipment: Activity & Scan
_LAYER_FOLK = 22              # Sediment: Folk Classification
_LAYER_SEISMIC = 34           # Seismic Reflection
_LAYER_WELLS = 39             # Hydrocarbon Wells

_DEFAULT_RADIUS_M = 5_000
_MAX_RADIUS_M = 50_000
_MAX_PER_LAYER = 25
_HTTP_TIMEOUT_S = 8.0
_USER_AGENT = "geomcp.dev/1.0 (+https://geomcp.dev)"

_ATTRIBUTION = (
    "Contains BGS © UKRI. Licensed under the Open Government Licence v3.0. "
    "Source: BGS GeoIndex Offshore (live query). Hydrocarbon well headers "
    "supplied by the North Sea Transition Authority and republished by BGS."
)

log = logging.getLogger(__name__)


async def marine_geology_uk(
    lat: float,
    lon: float,
    radius_m: int = _DEFAULT_RADIUS_M,
) -> dict[str, Any]:
    """Find BGS GeoIndex Offshore samples, sediment, seismic, and wells
    near a marine point.

    Queries four BGS GeoIndex Offshore layers in parallel and returns
    the matched features grouped by type. Each feature includes a
    direct ``scan_url`` to the BGS / NSTA archive when one exists, so
    a GIS user can pull the original PDF log or data pack without
    navigating BGS GeoIndex by hand.

    Useful for marine site-screening, EIA literature reviews, cable
    route engineering, and anywhere an agent needs to know what
    historical geophysical / geotechnical / sedimentological evidence
    the public scientific record holds for a location.

    Coverage is **UK Continental Shelf**. Onshore points return zero.

    Arguments:
        lat: WGS84 latitude, -90..90.
        lon: WGS84 longitude, -180..180.
        radius_m: search radius in metres, default 5000, capped at 50000.

    Returns:
        {
          "center": {"lat", "lon", "radius_m"},
          "totals": {"samples", "sediment_classifications",
                     "seismic_lines", "hydrocarbon_wells"},
          "samples":     [...],   # equipment-tagged sample points
          "sediment_classifications": [...],  # Folk-classified PSA points
          "seismic_lines": [...],  # 2D seismic survey lines
          "hydrocarbon_wells": [...],  # UKCS wells with status + operator
          "source": "BGS GeoIndex Offshore",
          "attribution": "..."
        }

    Each list is capped at 25 entries (nearest first). On invalid
    input returns ``{"error": ..., "message": ...}``. Upstream failure
    on any sublayer falls through with a partial result + a
    ``warnings`` list rather than failing the whole call.
    """
    err = validate_wgs84(lat, lon) or validate_radius_m(radius_m, max_m=_MAX_RADIUS_M)
    if err is not None:
        return err

    async with httpx.AsyncClient(
        timeout=_HTTP_TIMEOUT_S,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        samples_t, folk_t, seismic_t, wells_t = await asyncio.gather(
            _query_layer(client, _LAYER_SAMPLES, lon, lat, radius_m),
            _query_layer(client, _LAYER_FOLK, lon, lat, radius_m),
            _query_layer(client, _LAYER_SEISMIC, lon, lat, radius_m),
            _query_layer(client, _LAYER_WELLS, lon, lat, radius_m),
            return_exceptions=False,
        )

    warnings: list[str] = []
    samples = _process_point_layer(
        samples_t, lat, lon, _row_sample, warnings, "samples",
    )
    sediment = _process_point_layer(
        folk_t, lat, lon, _row_sediment, warnings, "sediment_classifications",
    )
    seismic = _process_line_layer(
        seismic_t, lat, lon, _row_seismic, warnings, "seismic_lines",
    )
    wells = _process_point_layer(
        wells_t, lat, lon, _row_well, warnings, "hydrocarbon_wells",
    )

    out: dict[str, Any] = {
        "center": {"lat": lat, "lon": lon, "radius_m": radius_m},
        "totals": {
            "samples": len(samples),
            "sediment_classifications": len(sediment),
            "seismic_lines": len(seismic),
            "hydrocarbon_wells": len(wells),
        },
        "samples": samples[:_MAX_PER_LAYER],
        "sediment_classifications": sediment[:_MAX_PER_LAYER],
        "seismic_lines": seismic[:_MAX_PER_LAYER],
        "hydrocarbon_wells": wells[:_MAX_PER_LAYER],
        "source": "BGS GeoIndex Offshore",
        "attribution": _ATTRIBUTION,
    }
    if warnings:
        out["warnings"] = warnings
    return out


# ---------------------------------------------------------------------------
# Per-layer query
# ---------------------------------------------------------------------------


async def _query_layer(
    client: httpx.AsyncClient,
    layer_id: int,
    lon: float, lat: float, radius_m: int,
) -> dict[str, Any] | Exception:
    """Spatial query against a single BGS Offshore sublayer. Returns the
    raw ArcGIS response, or the exception (so the caller can record a
    warning rather than fail the whole composite)."""
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "outSR": "4326",
        "distance": str(radius_m),
        "units": "esriSRUnit_Meter",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "resultRecordCount": "100",
        "f": "json",
    }
    try:
        resp = await client.get(f"{_BGS_BASE}/{layer_id}/query", params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        log.warning("BGS Offshore layer %d query failed: %s", layer_id, exc)
        return exc


# ---------------------------------------------------------------------------
# Result processing — points and lines have different geometry shapes
# ---------------------------------------------------------------------------


def _process_point_layer(
    raw: Any,
    lat: float, lon: float,
    row_fn,
    warnings: list[str],
    name: str,
) -> list[dict[str, Any]]:
    if isinstance(raw, Exception):
        warnings.append(f"{name}: upstream unavailable ({type(raw).__name__})")
        return []
    feats = (raw or {}).get("features", []) or []
    enriched: list[tuple[float, dict[str, Any]]] = []
    for f in feats:
        attrs = f.get("attributes", {}) or {}
        geom = f.get("geometry", {}) or {}
        x, y = geom.get("x"), geom.get("y")
        if x is None or y is None:
            continue
        d = _haversine_m(lat, lon, y, x)
        enriched.append((d, row_fn(attrs, d)))
    enriched.sort(key=lambda t: t[0])
    return [r for _, r in enriched]


def _process_line_layer(
    raw: Any,
    lat: float, lon: float,
    row_fn,
    warnings: list[str],
    name: str,
) -> list[dict[str, Any]]:
    if isinstance(raw, Exception):
        warnings.append(f"{name}: upstream unavailable ({type(raw).__name__})")
        return []
    feats = (raw or {}).get("features", []) or []
    enriched: list[tuple[float, dict[str, Any]]] = []
    for f in feats:
        attrs = f.get("attributes", {}) or {}
        geom = f.get("geometry", {}) or {}
        paths = geom.get("paths") or []
        if not paths:
            continue
        # Distance to closest vertex on any path. Good enough for
        # ranking — true line distance would require a polyline-point
        # projection that's overkill here.
        d = min(
            (_haversine_m(lat, lon, vy, vx) for path in paths for vx, vy in path),
            default=float("inf"),
        )
        if d == float("inf"):
            continue
        enriched.append((d, row_fn(attrs, d)))
    enriched.sort(key=lambda t: t[0])
    return [r for _, r in enriched]


# ---------------------------------------------------------------------------
# Per-layer row formatters
# ---------------------------------------------------------------------------


def _row_sample(a: dict[str, Any], distance_m: float) -> dict[str, Any]:
    return {
        "sample_name": a.get("SAMPLE_NAME"),
        "equipment_type": a.get("EQUIPMENT_TYPE"),
        "cruise": a.get("CRUISE"),
        "ship": a.get("SHIP"),
        "client": a.get("CLIENT"),
        "contractor": a.get("CONTRACTOR"),
        "water_depth_m": _num_or_none(a.get("WATER_DEPTH")),
        "terminal_depth": _num_or_none(a.get("TERMINAL_DEPTH")),
        "geol_summary": a.get("GEOL_SUMMARY"),
        "image_url": a.get("IMAGE_URL"),
        "report_url": a.get("OFFSHORE_REPORT"),
        "release_date": _epoch_ms_to_iso(a.get("RELEASE_DATE")),
        "distance_m": round(distance_m, 1),
    }


def _row_sediment(a: dict[str, Any], distance_m: float) -> dict[str, Any]:
    return {
        "sample_name": a.get("SAMPLE_NAME"),
        "folk_class": a.get("FOLK_CLASS"),
        "folk_short": a.get("FOLK"),
        "gravel_pct": _num_or_none(a.get("GRAV")),
        "sand_pct": _num_or_none(a.get("SAND")),
        "mud_pct": _num_or_none(a.get("MUD")),
        "equipment_type": a.get("EQUIPMENT_TYPE"),
        "water_depth_m": _num_or_none(a.get("WATER_DEPTH")),
        "depth_top": _num_or_none(a.get("DEPTH_TOP")),
        "depth_base": _num_or_none(a.get("DEPTH_BASE")),
        "distance_m": round(distance_m, 1),
    }


def _row_seismic(a: dict[str, Any], distance_m: float) -> dict[str, Any]:
    return {
        "cruise": a.get("CRUISE"),
        "survey_line": a.get("SVY_LINE"),
        "cruise_line": a.get("CRUISE_LINE"),
        "geophysical_equipment": a.get("GEOPHYS_EQUIP"),
        "line_length_m": _num_or_none(a.get("LINE_LENGTH")),
        "client": a.get("CLIENT"),
        "contractor": a.get("CONTRACTOR"),
        "scan_url": a.get("SCAN_URL"),
        "scan_download_url": a.get("SCAN_DOWNLOAD_URL"),
        "cruise_data_url": a.get("CRUISE_DATA_URL"),
        "release_date": _epoch_ms_to_iso(a.get("RELEASE_DATE")),
        "distance_m": round(distance_m, 1),
    }


def _row_well(a: dict[str, Any], distance_m: float) -> dict[str, Any]:
    return {
        "well_name": a.get("WELLNAME"),
        "den_number": a.get("DEN_NUMBER"),
        "licence": a.get("LICENCE"),
        "quadrant_block": _quadrant_block(a),
        "field_name": a.get("FIELDNAME"),
        "well_class": a.get("WELL_CLASS"),
        "well_status": a.get("WELL_STATUS"),
        "current_owner": a.get("CURRENT_OWNER"),
        "original_operator": a.get("ORIGINAL_OPERATOR"),
        "spud_date": _epoch_ms_to_iso(a.get("SPUD_DATE")),
        "completion_date": _epoch_ms_to_iso(a.get("COMPLETION_DATE")),
        "release_date": _epoch_ms_to_iso(a.get("RELEASE_DATE")),
        "water_depth_m": _num_or_none(a.get("WATER_DEPTH_M")),
        "total_depth_m": _num_or_none(a.get("TD_M")),
        "true_vertical_depth_m": _num_or_none(a.get("TVD_M")),
        "distance_m": round(distance_m, 1),
    }


def _quadrant_block(a: dict[str, Any]) -> str | None:
    """UK Continental Shelf well identifier — quadrant/block(suffix), e.g.
    ``48/04`` or ``13/30a``. Built from three separate columns in the
    BGS layer for caller convenience."""
    q = a.get("QUADRANT")
    b = a.get("BLOCK")
    s = a.get("BLOCK_SUFFIX") or ""
    if q is None or b is None:
        return None
    return f"{q}/{b}{s}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres. Adequate for the small radii
    these tools use — well under the 0.5 % error of the spherical
    model at any UK latitude."""
    r = 6_371_008.8  # mean Earth radius, metres
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    h = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _num_or_none(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _epoch_ms_to_iso(v: Any) -> str | None:
    if v is None or v == "":
        return None
    try:
        from datetime import datetime, timezone
        ts = int(v) / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        return None
