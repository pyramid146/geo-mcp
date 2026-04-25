"""Marine Data Exchange (Crown Estate) — public survey-metadata search.

The Crown Estate's Marine Data Exchange (MDX) is the deposit point for
all survey data collected by UK offshore-renewable lessees. By the
terms of the Crown Estate licence, developers must deposit their
geophysical, geotechnical, ecological, ornithological and met-ocean
survey data in MDX after a confidentiality embargo expires (typically
1–2 years). Once public, the data is licensed under the Crown Estate's
Open Data Licence (effectively OGLv3-flavoured).

This tool is a **discovery layer** over MDX's public series catalogue.
Given a WGS84 point + radius, it returns the metadata for all survey
*series* that intersect the query area, including the public download
URL for each. It does NOT fetch the actual survey files — those range
from MB-scale reports to multi-GB point clouds and SEGY datasets,
which an LLM agent should never inhale into context. The tool's value
is exposing what data EXISTS at a point so the user can choose what to
download.

Endpoint: ArcGIS Feature Service — public, anonymous, no API key.
URL:      services2.arcgis.com/PZklK9Q45mfMFuZs/...
Probed:   April 2026; ToS at marinedataexchange.co.uk/content/info/
          terms-of-use grants a non-exclusive licence to copy and use,
          with no automation/scraping clauses.

Coverage: UK seabed (territorial waters + UK Continental Shelf). Data
density is *very* high in offshore-wind zones (Dogger Bank, Hornsea,
East Anglia, Moray Firth, Celtic Sea Round 5) and sparse outside them.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from geo_mcp.tools._validators import validate_radius_m, validate_wgs84

_MDX_ENDPOINT = (
    "https://services2.arcgis.com/PZklK9Q45mfMFuZs/arcgis/rest/services/"
    "MDE_SeriesExtents_PublicPolygons/FeatureServer/0/query"
)
_DEFAULT_RADIUS_M = 5_000     # marine queries are wider than onshore by default
_MAX_RADIUS_M = 50_000        # 50 km cap — bigger and the result set explodes
_MAX_RECORDS_RETURNED = 50
_HTTP_TIMEOUT_S = 8.0
_USER_AGENT = "geomcp.dev/1.0 (+https://geomcp.dev)"

_ATTRIBUTION = (
    "Survey-series metadata © The Crown Estate, supplied via the "
    "Marine Data Exchange (marinedataexchange.co.uk). Licensed under "
    "the Crown Estate Open Data Licence. Individual survey datasets "
    "may carry additional licence conditions — check each series page."
)

log = logging.getLogger(__name__)


async def marine_surveys_uk(
    lat: float,
    lon: float,
    radius_m: int = _DEFAULT_RADIUS_M,
    include_research: bool = False,
) -> dict[str, Any]:
    """Find UK offshore survey datasets near a marine point.

    Queries The Crown Estate's Marine Data Exchange (MDX) public series
    catalogue for survey programmes that intersect the given area. MDX
    holds the data deposited by every UK offshore-wind, marine-licence,
    and seabed-mineral lessee — geophysical (multibeam, side-scan,
    sub-bottom profiler, magnetometer), geotechnical (CPTs, vibrocores,
    boreholes), benthic ecology, ornithology, marine mammals, fish,
    archaeology, and met-ocean. Coverage is dense inside offshore-wind
    zones (Dogger Bank, Hornsea, East Anglia, Moray Firth, Celtic Sea)
    and sparse outside them.

    Each returned series is a *programme* of survey work (often
    spanning months and many vessels), not a single file. The
    ``portal_url`` links to the MDX series page where the actual
    reports + datasets are listed for direct download. No login is
    required to download MDX-hosted files.

    Use this tool when an agent needs to know what survey evidence
    exists at a coastal or offshore site — e.g. for desk-based
    pre-FEED screening, EIA literature review, cable-route feasibility,
    or decommissioning baseline characterisation.

    By default, **research-phase programmes are excluded** from the
    series list because their polygons typically span the entire UK
    EEZ (e.g. Cefas / Natural England / JNCC OWEC research) and would
    swamp any localised query. Their count is still surfaced under
    ``research_count`` so the caller knows broader research evidence
    exists and can opt in via ``include_research=True``.

    Coverage is **UK marine waters** (territorial sea + UK Continental
    Shelf). Onshore points generally return zero site-specific
    results.

    Arguments:
        lat: WGS84 latitude, -90..90.
        lon: WGS84 longitude, -180..180.
        radius_m: search radius in metres, default 5000, capped at 50000.
        include_research: include nationwide research-phase programmes
            in the ``series`` list. Default False (their count is still
            returned in ``research_count``).

    Returns:
        {
          "center": {"lat", "lon", "radius_m"},
          "count": int,                       # site-specific series count
          "research_count": int,              # nationwide research programmes also intersecting
          "by_phase": {"<phase>": int, ...},  # group by Development_Phase
          "by_theme": {"<theme>": int, ...},  # group by Themes (site-specific only)
          "series": [
              {"series_id", "name", "site",
               "phase", "themes", "methodologies",
               "start_date", "end_date",
               "n_collections", "portal_url"},
              ...                              # up to 50, newest first
          ],
          "source": "Marine Data Exchange — series catalogue",
          "attribution": "..."
        }

    On invalid input, returns ``{"error": ..., "message": ...}``. If
    the upstream is unreachable, returns
    ``{"error": "upstream_unavailable", "message": ...}`` rather than
    raising.
    """
    err = validate_wgs84(lat, lon) or validate_radius_m(radius_m, max_m=_MAX_RADIUS_M)
    if err is not None:
        return err

    # ArcGIS distance query in WGS84: pass geometry as a point, distance
    # in metres, with explicit units. The service projects internally.
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "outSR": "4326",
        "distance": str(radius_m),
        "units": "esriSRUnit_Meter",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": (
            "Series_ID,SeriesName,DevelopmentSite,Development_Phase,"
            "Methodology_Keywords,Themes,Start_date,End_date,"
            "No_of_Collections,PublicURL,New_Portal_URL"
        ),
        "returnGeometry": "false",
        "resultRecordCount": "300",
        "f": "json",
    }

    try:
        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT_S,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            resp = await client.get(_MDX_ENDPOINT, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        log.warning("MDX series query failed: %s", exc)
        return {
            "error": "upstream_unavailable",
            "message": f"Marine Data Exchange could not be reached: {exc}",
            "center": {"lat": lat, "lon": lon, "radius_m": radius_m},
        }

    features = data.get("features", []) or []
    all_rows = [_series_row(f.get("attributes", {}) or {}) for f in features]

    site_rows = [r for r in all_rows if not _is_research_phase(r.get("phase"))]
    research_rows = [r for r in all_rows if _is_research_phase(r.get("phase"))]
    visible_rows = all_rows if include_research else site_rows

    # Newest-first. Series with no end_date sink to the bottom.
    visible_rows.sort(key=lambda r: r.get("end_date") or "", reverse=True)

    by_phase: dict[str, int] = {}
    by_theme: dict[str, int] = {}
    for r in site_rows:  # phase + theme stats reflect the site-specific cut
        phase = (r.get("phase") or "unspecified").strip()
        by_phase[phase] = by_phase.get(phase, 0) + 1
        for t in (r.get("themes") or []):
            by_theme[t] = by_theme.get(t, 0) + 1

    return {
        "center": {"lat": lat, "lon": lon, "radius_m": radius_m},
        "count": len(site_rows),
        "research_count": len(research_rows),
        "by_phase": by_phase,
        "by_theme": by_theme,
        "series": visible_rows[:_MAX_RECORDS_RETURNED],
        "source": "Marine Data Exchange — series catalogue",
        "attribution": _ATTRIBUTION,
    }


def _is_research_phase(phase: Any) -> bool:
    """Research-phase programmes typically have national-extent polygons
    (Cefas / NE / JNCC / OWEC) that intersect any UK coastal point and
    swamp localised queries. Treat them as a separate bucket. The MDX
    data has trailing-whitespace variants (``"Research "``) so normalise."""
    if not isinstance(phase, str):
        return False
    return phase.strip().lower() == "research"


def _series_row(attrs: dict[str, Any]) -> dict[str, Any]:
    return {
        "series_id": attrs.get("Series_ID"),
        "name": attrs.get("SeriesName"),
        "site": attrs.get("DevelopmentSite"),
        "phase": attrs.get("Development_Phase"),
        "themes": _split_pipe(attrs.get("Themes")),
        "methodologies": _split_pipe(attrs.get("Methodology_Keywords")),
        "start_date": _epoch_ms_to_iso(attrs.get("Start_date")),
        "end_date": _epoch_ms_to_iso(attrs.get("End_date")),
        "n_collections": _int_or_none(attrs.get("No_of_Collections")),
        "portal_url": attrs.get("New_Portal_URL") or attrs.get("PublicURL"),
    }


def _split_pipe(v: Any) -> list[str] | None:
    """MDX free-text fields use ``|`` as a separator. Return a clean list
    or None if absent."""
    if not v or not isinstance(v, str):
        return None
    parts = [p.strip() for p in v.split("|") if p.strip()]
    return parts or None


def _epoch_ms_to_iso(v: Any) -> str | None:
    """ArcGIS dates come as milliseconds-since-epoch ints. Convert to a
    ``YYYY-MM-DD`` string in UTC. Return None for absent / unparseable."""
    if v is None or v == "":
        return None
    try:
        ts = int(v) / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        return None


def _int_or_none(v: Any) -> int | None:
    try:
        if v is None or v == "":
            return None
        return int(v)
    except (TypeError, ValueError):
        return None
