"""ADMIRALTY SeaBed Mapping Service — bathymetric survey discovery.

UKHO publishes a public, anonymous catalogue of every ADMIRALTY-deposited
bathymetric survey at ``seabed.admiralty.co.uk``. Each record carries a
title, start/end dates, spatial resolution, file size, and a polygon
showing the survey footprint. The actual data files (BAG / ASCII grids)
require a free Microsoft B2C login to download — but the metadata
catalogue itself is open.

This tool wraps the catalogue endpoint and lets an LLM agent answer
"what UKHO bathymetric surveys cover this point?" without ever
authenticating. Discovery only — the tool returns the survey IDs +
the seabed.admiralty.co.uk portal URL where the user can register
(free) and pull the actual ZIPs.

Caching: the catalogue is ~47 MB and changes weekly at most. We cache
it on disk for 24 h and pre-process bboxes for cheap spatial filtering.
First call after a fresh start fetches; subsequent calls hit the cache.

Endpoint: ``seabedmappingservice-live.azurewebsites.net/api/featuremetadata``
Anonymous GET, JSON, no rate limit clauses observed in T&Cs. Crown
copyright UK Hydrographic Office.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from pathlib import Path
from typing import Any

import httpx

from geo_mcp.tools._validators import validate_radius_m, validate_wgs84

_CATALOGUE_URL = (
    "https://seabedmappingservice-live.azurewebsites.net/api/featuremetadata"
)
_PORTAL_BASE = "https://seabed.admiralty.co.uk"

_DEFAULT_RADIUS_M = 5_000
_MAX_RADIUS_M = 50_000
_MAX_RECORDS_RETURNED = 50
_CACHE_TTL_S = 24 * 3600
_CATALOGUE_FETCH_TIMEOUT_S = 60.0
_USER_AGENT = "geomcp.dev/1.0 (+https://geomcp.dev)"

# On-disk cache. /tmp is fine — not security-sensitive, and a fresh
# fetch is cheap if the file vanishes. Path is fixed so multiple worker
# processes share the cache.
_CACHE_PATH = Path("/tmp/geomcp_admiralty_catalogue.json")

_ATTRIBUTION = (
    "Survey metadata © Crown copyright UK Hydrographic Office, sourced "
    "from the public ADMIRALTY SeaBed Mapping Service catalogue at "
    "seabed.admiralty.co.uk. Dataset downloads require a free "
    "registration on the ADMIRALTY portal — this tool returns metadata "
    "+ portal URLs only, never the data files themselves."
)

log = logging.getLogger(__name__)

# Process-global indexed cache — list of (bbox, record) tuples.
_indexed_cache: list[tuple[tuple[float, float, float, float], dict[str, Any]]] | None = None
_cache_loaded_at: float = 0.0
_cache_lock = asyncio.Lock()


async def marine_admiralty_uk(
    lat: float,
    lon: float,
    radius_m: int = _DEFAULT_RADIUS_M,
) -> dict[str, Any]:
    """Find UKHO ADMIRALTY bathymetric surveys near a marine point.

    Searches the public ADMIRALTY SeaBed Mapping Service catalogue
    (~7,000 surveys) for any whose recorded footprint intersects a
    circle of ``radius_m`` around the input point. Each match is
    returned with its title, dates, spatial resolution, file size,
    bounding box, and a portal URL where a free signed-in user can
    pull the ZIP.

    UKHO commercial chart products (AVCS, Bathymetric Data Portal raw
    ENCs, AIS Density Maps) are NOT covered by this tool — they aren't
    in this open catalogue. What IS here is the deposited bathymetric
    survey archive going back to the 1950s, much of which is the
    underlying source for the EMODnet aggregate DTM.

    Coverage: UK + adjacent waters, both contemporary multibeam and
    legacy single-beam soundings. Onshore points return zero. Inland
    UK lakes are not covered (the catalogue is sea/seabed only).

    Arguments:
        lat: WGS84 latitude, -90..90.
        lon: WGS84 longitude, -180..180.
        radius_m: search radius in metres, default 5000, capped at 50000.

    Returns:
        {
          "center": {"lat", "lon", "radius_m"},
          "count": int,                              # total matches
          "surveys": [
              {"id", "title",
               "start_date", "end_date",
               "spatial_resolution",                 # human-readable
               "data_size_bytes",
               "bbox": [west, south, east, north],
               "portal_url"},
              ...                                    # cap 50, newest first
          ],
          "source": "ADMIRALTY SeaBed Mapping Service",
          "attribution": "...",
          "notes": "Downloads require free registration at seabed.admiralty.co.uk"
        }

    On invalid input returns ``{"error": ..., "message": ...}``.
    Catalogue fetch failure returns
    ``{"error": "upstream_unavailable", "message": ...}``.
    """
    err = validate_wgs84(lat, lon) or validate_radius_m(radius_m, max_m=_MAX_RADIUS_M)
    if err is not None:
        return err

    try:
        indexed = await _get_indexed_catalogue()
    except (httpx.HTTPError, OSError, ValueError) as exc:
        log.warning("ADMIRALTY catalogue fetch/cache failed: %s", exc)
        return {
            "error": "upstream_unavailable",
            "message": f"ADMIRALTY catalogue could not be loaded: {exc}",
            "center": {"lat": lat, "lon": lon, "radius_m": radius_m},
        }

    # Convert search radius to a degree bbox.
    dlat = radius_m / 111_000.0
    dlon = radius_m / (111_000.0 * max(0.1, math.cos(math.radians(lat))))
    search_bbox = (lon - dlon, lat - dlat, lon + dlon, lat + dlat)

    matches: list[dict[str, Any]] = []
    for record_bbox, record in indexed:
        if _bbox_overlap(record_bbox, search_bbox):
            matches.append(_format_record(record, record_bbox))

    matches.sort(key=lambda r: r.get("end_date") or "", reverse=True)

    return {
        "center": {"lat": lat, "lon": lon, "radius_m": radius_m},
        "count": len(matches),
        "surveys": matches[:_MAX_RECORDS_RETURNED],
        "source": "ADMIRALTY SeaBed Mapping Service",
        "attribution": _ATTRIBUTION,
        "notes": (
            "Downloads require free registration at seabed.admiralty.co.uk. "
            "This tool returns metadata only — never the actual ZIP files."
        ),
    }


# ---------------------------------------------------------------------------
# Catalogue load + indexing
# ---------------------------------------------------------------------------


async def _get_indexed_catalogue() -> list[tuple[tuple[float, float, float, float], dict[str, Any]]]:
    """Return the spatial index. Loads from disk cache or refetches if
    stale. Process-wide singleton; concurrent callers serialise through
    ``_cache_lock`` so we don't fan out 18 fetches of the 47 MB blob."""
    global _indexed_cache, _cache_loaded_at
    async with _cache_lock:
        now = time.time()
        if _indexed_cache is not None and (now - _cache_loaded_at) < _CACHE_TTL_S:
            return _indexed_cache

        # Disk cache check
        raw: dict[str, Any] | None = None
        if _CACHE_PATH.exists():
            mtime = _CACHE_PATH.stat().st_mtime
            if (now - mtime) < _CACHE_TTL_S:
                try:
                    with open(_CACHE_PATH) as f:
                        raw = json.load(f)
                    log.info("ADMIRALTY catalogue: served from disk cache")
                except (OSError, ValueError):
                    raw = None

        if raw is None:
            log.info("ADMIRALTY catalogue: fetching from upstream (~47 MB)")
            async with httpx.AsyncClient(
                timeout=_CATALOGUE_FETCH_TIMEOUT_S,
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                resp = await client.get(_CATALOGUE_URL)
                resp.raise_for_status()
                raw = resp.json()
            try:
                _CACHE_PATH.write_text(json.dumps(raw))
            except OSError as exc:  # pragma: no cover — disk full etc.
                log.warning("ADMIRALTY catalogue: cache write failed: %s", exc)

        _indexed_cache = _build_index(raw)
        _cache_loaded_at = now
        return _indexed_cache


def _build_index(
    raw: dict[str, Any],
) -> list[tuple[tuple[float, float, float, float], dict[str, Any]]]:
    """Compute one bbox per record. Skips records with unparseable
    geometry. Iterating ~7,000 records on each query is well under a
    millisecond — no need for an R-tree."""
    records = (raw.get("data") or {}).get("metadataDataset") or []
    out: list[tuple[tuple[float, float, float, float], dict[str, Any]]] = []
    for r in records:
        sp = r.get("derivedSpatialExtent") or {}
        coords = sp.get("coordinates") or []
        bbox = _coords_bbox(coords)
        if bbox is None:
            continue
        out.append((bbox, r))
    return out


def _coords_bbox(coords: Any) -> tuple[float, float, float, float] | None:
    """Recurse through nested coordinate lists ([lon, lat] leaves) and
    return ``(west, south, east, north)``. None if no points found."""
    lats: list[float] = []
    lons: list[float] = []

    def walk(x: Any) -> None:
        if isinstance(x, list):
            # Leaf: [lon, lat] (length 2 of numbers)
            if (
                len(x) == 2
                and isinstance(x[0], (int, float))
                and isinstance(x[1], (int, float))
            ):
                lons.append(float(x[0]))
                lats.append(float(x[1]))
                return
            for sub in x:
                walk(sub)

    walk(coords)
    if not lats:
        return None
    return (min(lons), min(lats), max(lons), max(lats))


def _bbox_overlap(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    """Standard separating-axis bbox overlap. ``(west, south, east, north)``
    on each side."""
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


# ---------------------------------------------------------------------------
# Record formatting
# ---------------------------------------------------------------------------


def _format_record(
    r: dict[str, Any],
    bbox: tuple[float, float, float, float],
) -> dict[str, Any]:
    return {
        "id": r.get("id"),
        "title": r.get("resourceTitle"),
        "start_date": _trim_iso(r.get("startDate")),
        "end_date": _trim_iso(r.get("endDate")),
        "spatial_resolution": _format_resolution(r.get("datasetSpatialResolutions")),
        "data_size_bytes": _sum_size(r.get("datafiles")),
        "bbox": [round(v, 6) for v in bbox],
        "portal_url": _PORTAL_BASE,
    }


def _format_resolution(arr: Any) -> str | None:
    """Translate ``datasetSpatialResolutions`` into a human-readable
    string. The catalogue uses three rtype values:

    * ``distance`` — value is metres of grid spacing (modern surveys, e.g. ``2 m grid``)
    * ``equivalent scale`` — value is the denominator of an old map scale (``1:80,000``)
    * ``inapplicable`` — return None
    """
    if not isinstance(arr, list) or not arr:
        return None
    first = arr[0]
    if not isinstance(first, dict):
        return None
    val = first.get("spatialResolution")
    rtype = ((first.get("spatialResolutionType") or {})
             .get("spatialResolutionType") or "")
    if val is None:
        return None
    rtype_lc = str(rtype).lower()
    if rtype_lc == "equivalent scale":
        return f"1:{int(val):,}"
    if rtype_lc == "distance":
        # Whole-metre grid is the common case. Show fractional only if
        # the number isn't integer.
        if float(val).is_integer():
            return f"{int(val)} m grid"
        return f"{val} m grid"
    if rtype_lc == "inapplicable":
        return None
    return f"{val} ({rtype})" if rtype else f"{val}"


def _sum_size(arr: Any) -> int:
    if not isinstance(arr, list):
        return 0
    total = 0
    for f in arr:
        if isinstance(f, dict):
            v = f.get("size")
            try:
                total += int(v or 0)
            except (TypeError, ValueError):
                pass
    return total


def _trim_iso(v: Any) -> str | None:
    """Catalogue dates are full ISO with ``.000Z``. Just return YYYY-MM-DD."""
    if not isinstance(v, str) or len(v) < 10:
        return None
    return v[:10]
