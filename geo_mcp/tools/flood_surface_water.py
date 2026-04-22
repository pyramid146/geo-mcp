from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from geo_mcp.data_access.projections import to_osgb
from geo_mcp.tools._validators import validate_wgs84

_WMS_ENDPOINT = (
    "https://environment.data.gov.uk/spatialdata/"
    "nafra2-risk-of-flooding-from-surface-water/wms"
)
_LAYER = "rofsw"
_ATTRIBUTION = (
    "Contains Environment Agency data © Environment Agency copyright and/or "
    "database right 2026. Risk of Flooding from Surface Water (RoFSW). "
    "Licensed under the Open Government Licence v3.0."
)

# GetFeatureInfo text/plain parser. Example response body:
#   Results for FeatureType '...':
#   --------------------------------------------
#   risk_band = Medium
#   confidence = null
#   ...
_RISK_RE = re.compile(r"^\s*risk_band\s*=\s*(\S+)", re.MULTILINE)

_HTTP_TIMEOUT_S = 4.0
_QUERY_TILE_PX = 100
_QUERY_TILE_M = 100  # 100 m bbox centred on the point
_VALID_BANDS = {"High", "Medium", "Low"}

log = logging.getLogger(__name__)


async def surface_water_risk_uk(lat: float, lon: float) -> dict[str, Any]:
    """Return the EA Risk of Flooding from Surface Water (RoFSW) band at a WGS84 point.

    Surface-water (pluvial) flooding is the kind that happens when heavy
    rain overwhelms drains, soaks the ground, and pools on streets or
    runs off overland — independent of whether rivers or the sea are
    involved. It's the source that planners and homeowners most often
    under-weight because a property "away from any river" can still sit
    in a surface-water risk pocket.

    EA likelihood bands (same thresholds as RoFRS for rivers/sea):
      - **High**       ≥3.3% annual chance
      - **Medium**     1 – 3.3%
      - **Low**        0.1 – 1%
      - **Very Low**   <0.1% — implicit: no RoFSW polygon covers the point

    Complements the other flood tools:
      * ``flood_risk_uk``              — planning zones (fluvial + sea, no defences)
      * ``flood_risk_probability_uk``  — RoFRS, fluvial + sea probability with defences
      * ``surface_water_risk_uk``      — *this*, surface water / pluvial
      * ``historic_floods_uk``         — has the point actually flooded

    Coverage is **England only**. Welsh, Scottish, and Northern Irish
    points return ``band: "Very Low"`` (no polygon covers them) but
    that's coverage-gap, not an assessment — treat with the
    ``coverage_note`` in mind.

    The live query hits the Environment Agency's RoFSW WMS
    (GetFeatureInfo). Typical latency 200 – 500 ms. If the EA service
    is unreachable, returns ``{"error": "upstream_unavailable", …}``
    rather than raising.

    Arguments:
        lat: WGS84 latitude, -90..90.
        lon: WGS84 longitude, -180..180.

    Returns:
        {
          "band": "High" | "Medium" | "Low" | "Very Low",
          "coverage_note": "...",
          "source": "EA RoFSW (WMS GetFeatureInfo)",
          "attribution": "..."
        }
    """
    err = validate_wgs84(lat, lon)
    if err is not None:
        return err

    east, north = to_osgb().transform(lon, lat)
    half = _QUERY_TILE_M // 2
    params = {
        "service": "WMS",
        "version": "1.3.0",
        "request": "GetFeatureInfo",
        "layers": _LAYER,
        "query_layers": _LAYER,
        "crs": "EPSG:27700",
        "bbox": f"{east-half},{north-half},{east+half},{north+half}",
        "width": str(_QUERY_TILE_PX),
        "height": str(_QUERY_TILE_PX),
        "i": str(_QUERY_TILE_PX // 2),
        "j": str(_QUERY_TILE_PX // 2),
        "info_format": "text/plain",
    }

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S) as client:
            resp = await client.get(_WMS_ENDPOINT, params=params)
            resp.raise_for_status()
            body = resp.text
    except httpx.HTTPError as exc:
        log.warning("RoFSW WMS query failed: %s", exc)
        return {
            "error": "upstream_unavailable",
            "message": f"EA RoFSW WMS could not be reached: {exc}",
        }

    m = _RISK_RE.search(body)
    if m:
        raw = m.group(1).strip().strip("'\"")
        band = raw if raw in _VALID_BANDS else "Very Low"
    else:
        band = "Very Low"

    return {
        "band": band,
        "coverage_note": (
            "RoFSW covers England only. Points in Scotland, Wales, or Northern "
            "Ireland receive 'Very Low' here because no polygon covers them — "
            "that's a coverage gap, not an assessment."
        ),
        "source": "EA RoFSW (WMS GetFeatureInfo)",
        "attribution": _ATTRIBUTION,
    }
