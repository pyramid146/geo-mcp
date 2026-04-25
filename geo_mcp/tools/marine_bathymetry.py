"""EMODnet Bathymetry — depth at point + contributing surveys.

Why EMODnet, not UKHO directly:

UKHO's own ADMIRALTY services (Bathymetric Data Portal, AVCS, AIS
Density, Marine Data Portal) are commercial — Crown-Copyright,
licence-gated, no anonymous APIs, redistribution forbidden.

EMODnet Bathymetry is the canonical open alternative for UK waters.
It aggregates UKHO + Dutch RWS + Norwegian Mapping Authority + IFREMER
+ many EU sources into a 1/16 arc-minute (~115 m) Digital Terrain
Model. Critically, the WFS exposes a **source_references** layer that
tells you, for any point, which underlying surveys went into the DTM
— so an LLM agent can surface "the depth here is X, sourced from
UKHO survey Y deposited 2022" rather than just "X metres".

Both endpoints are anonymous OGC services, CC-BY 4.0, designed for
machine access (``Fees=None``, ``AccessConstraints=None``).

* WMS GetFeatureInfo — point depth, gridded DTM.
* WFS source_references — survey lineage polygons intersecting a bbox.

Coverage: full UK EEZ + adjacent waters. Returns null/empty for
inland points and unsurveyed deep ocean (where GEBCO global fallback
applies — flagged in the response so the caller knows the depth
isn't from a real local survey).
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

import httpx

from geo_mcp.tools._validators import validate_radius_m, validate_wgs84

_WMS_ENDPOINT = "https://ows.emodnet-bathymetry.eu/wms"
_WFS_ENDPOINT = "https://ows.emodnet-bathymetry.eu/wfs"
_LAYER_DEPTH = "emodnet:mean"
_LAYER_SOURCES = "emodnet:source_references"

_DEFAULT_RADIUS_M = 1_000
_MAX_RADIUS_M = 50_000
_MAX_SURVEYS_RETURNED = 25
_HTTP_TIMEOUT_S = 8.0
_USER_AGENT = "geomcp.dev/1.0 (+https://geomcp.dev)"

_ATTRIBUTION = (
    "Bathymetry from EMODnet Bathymetry, "
    "https://emodnet.ec.europa.eu/en/bathymetry. "
    "Licensed CC-BY 4.0. Aggregates contributions from UKHO and other "
    "European hydrographic offices via the SeaDataNet CDI catalogue. "
    "ADMIRALTY chart products are commercially licensed and not included "
    "in this open derivative."
)

log = logging.getLogger(__name__)


async def marine_bathymetry_uk(
    lat: float,
    lon: float,
    radius_m: int = _DEFAULT_RADIUS_M,
) -> dict[str, Any]:
    """Get seabed depth and contributing surveys at a UK marine point.

    Two parallel calls into EMODnet Bathymetry:

    * WMS GetFeatureInfo on the gridded ``emodnet:mean`` DTM gives the
      depth at the exact point (negative metres below mean sea level).
    * WFS GetFeature on the ``emodnet:source_references`` layer lists
      every survey whose footprint intersects ``radius_m`` around the
      point — including UKHO, Dutch, Norwegian, French, etc. surveys
      that contributed to that DTM tile, with their EDMO institution
      IDs and direct SeaDataNet metadata URLs.

    Each survey is tagged ``release`` (which DTM release used it) and
    deduped to the most recent release per unique identifier — so a
    survey contributing to both the 2022 and 2024 DTMs only appears
    once. ``gebco_fallback=true`` if the only "surveys" found are
    GEBCO global grid entries (no real local hydrographic survey).

    The actual UKHO ADMIRALTY chart products are commercial and are
    NOT returned by this tool. For survey-level UKHO data, follow the
    SeaDataNet metadata URL — that's the authoritative source.

    Coverage: UK EEZ + adjacent EU waters. Returns null depth and
    empty surveys for inland points or unsurveyed deep ocean.

    Arguments:
        lat: WGS84 latitude, -90..90.
        lon: WGS84 longitude, -180..180.
        radius_m: search radius in metres for the survey-lineage WFS
            query, default 1000, capped at 50000. The depth value is
            point-precise regardless of radius.

    Returns:
        {
          "center": {"lat", "lon", "radius_m"},
          "depth_m": float | null,
          "contributing_surveys": [
              {"identifier", "type", "edmo_id",
               "release", "date_start", "date_end",
               "metadata_url"},
              ...                           # up to 25, newest release first
          ],
          "gebco_fallback": bool,           # true if only GEBCO entries
          "source": "EMODnet Bathymetry",
          "attribution": "..."
        }

    On invalid input returns ``{"error": ..., "message": ...}``. Each
    sub-call degrades independently — if WFS times out but WMS
    succeeds, depth still comes back with ``warnings: [...]``.
    """
    err = validate_wgs84(lat, lon) or validate_radius_m(radius_m, max_m=_MAX_RADIUS_M)
    if err is not None:
        return err

    async with httpx.AsyncClient(
        timeout=_HTTP_TIMEOUT_S,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        depth_t, surveys_t = await asyncio.gather(
            _query_depth(client, lat, lon),
            _query_surveys(client, lat, lon, radius_m),
            return_exceptions=False,
        )

    warnings: list[str] = []
    if isinstance(depth_t, Exception):
        warnings.append(f"depth: upstream unavailable ({type(depth_t).__name__})")
        depth_m = None
    else:
        depth_m = depth_t

    if isinstance(surveys_t, Exception):
        warnings.append(f"surveys: upstream unavailable ({type(surveys_t).__name__})")
        surveys: list[dict[str, Any]] = []
    else:
        surveys = surveys_t

    surveys = _dedupe_and_sort(surveys)
    gebco_only = bool(surveys) and all(_is_gebco(s) for s in surveys)

    out: dict[str, Any] = {
        "center": {"lat": lat, "lon": lon, "radius_m": radius_m},
        "depth_m": depth_m,
        "contributing_surveys": surveys[:_MAX_SURVEYS_RETURNED],
        "gebco_fallback": gebco_only,
        "source": "EMODnet Bathymetry",
        "attribution": _ATTRIBUTION,
    }
    if warnings:
        out["warnings"] = warnings
    return out


# ---------------------------------------------------------------------------
# Sub-queries
# ---------------------------------------------------------------------------


async def _query_depth(
    client: httpx.AsyncClient, lat: float, lon: float,
) -> float | None | Exception:
    """WMS GetFeatureInfo on the gridded DTM. Builds a small bbox around
    the point and asks for the centre pixel."""
    delta = 0.001  # ~111 m at equator — well within one DTM cell
    params = {
        "service": "WMS",
        "version": "1.3.0",
        "request": "GetFeatureInfo",
        "layers": _LAYER_DEPTH,
        "query_layers": _LAYER_DEPTH,
        "crs": "EPSG:4326",
        # WMS 1.3.0 with EPSG:4326 wants lat,lon ordering for bbox.
        "bbox": f"{lat - delta},{lon - delta},{lat + delta},{lon + delta}",
        "width": "11",
        "height": "11",
        "i": "5",
        "j": "5",
        "info_format": "application/json",
    }
    try:
        resp = await client.get(_WMS_ENDPOINT, params=params)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("EMODnet WMS depth query failed: %s", exc)
        return exc
    feats = (data or {}).get("features") or []
    if not feats:
        return None
    props = feats[0].get("properties") or {}
    raw = props.get("Depth")
    if raw is None:
        return None
    try:
        return round(float(raw), 2)
    except (TypeError, ValueError):
        return None


async def _query_surveys(
    client: httpx.AsyncClient, lat: float, lon: float, radius_m: int,
) -> list[dict[str, Any]] | Exception:
    """WFS GetFeature on the source_references layer. Returns a flat
    list of survey-property dicts (raw, undeduped)."""
    # Convert metres to a degrees-bbox. Latitude is constant; longitude
    # depends on cos(lat). Crude but fine inside UK waters.
    dlat = radius_m / 111_000.0
    dlon = radius_m / (111_000.0 * max(0.1, math.cos(math.radians(lat))))
    # NOTE: empirically the EMODnet WFS expects bbox in lon,lat order
    # despite WFS 2.0's nominal lat,lon convention for EPSG:4326. Don't
    # "fix" this without re-probing.
    bbox = f"{lon - dlon},{lat - dlat},{lon + dlon},{lat + dlat},EPSG:4326"
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": _LAYER_SOURCES,
        "bbox": bbox,
        "outputFormat": "application/json",
        "count": "200",
    }
    try:
        resp = await client.get(_WFS_ENDPOINT, params=params)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("EMODnet WFS surveys query failed: %s", exc)
        return exc

    rows: list[dict[str, Any]] = []
    for f in (data or {}).get("features") or []:
        p = f.get("properties") or {}
        rows.append({
            "identifier": p.get("identifier"),
            "type": p.get("type"),
            "edmo_id": p.get("edmo_id"),
            "release": p.get("release"),
            "date_start": _trim_date(p.get("date_start")),
            "date_end": _trim_date(p.get("date_end")),
            "metadata_url": p.get("metadata_url"),
        })
    return rows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dedupe_and_sort(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Same survey often appears once per DTM release (2016 / 2018 /
    2020 / 2022 / 2024). Keep only the entry from the most recent
    release per ``identifier``. Sort newest-release first."""
    by_id: dict[str, dict[str, Any]] = {}
    for r in rows:
        ident = r.get("identifier")
        if not ident:
            continue
        existing = by_id.get(ident)
        if existing is None or _release_int(r) > _release_int(existing):
            by_id[ident] = r
    return sorted(
        by_id.values(),
        key=lambda r: (_release_int(r), r.get("date_end") or ""),
        reverse=True,
    )


def _release_int(r: dict[str, Any]) -> int:
    """``release`` is a year string. Treat unknown as -1."""
    v = r.get("release")
    try:
        return int(str(v))
    except (TypeError, ValueError):
        return -1


def _is_gebco(r: dict[str, Any]) -> bool:
    """GEBCO entries are the global-grid fallback used where no real
    local survey exists. Identifier starts with ``GEBCO`` and there's
    no EDMO id."""
    ident = (r.get("identifier") or "").upper()
    return ident.startswith("GEBCO") and r.get("edmo_id") is None


def _trim_date(v: Any) -> str | None:
    """EMODnet date strings come like ``2022-12-31Z``. Strip the Z and
    return as plain ``YYYY-MM-DD``."""
    if not v or not isinstance(v, str):
        return None
    return v[:10]
