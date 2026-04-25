"""NSTA Open Data — petroleum + carbon-storage assets on the UKCS.

Two tiers of NSTA data exist; this tool wraps the OPEN tier:

* **Open Data** — published on NSTA's public ArcGIS Online org under
  the **NSTA Open User Licence** (Crown copyright, permissive re-use).
  720+ feature services covering survey footprints, wellbore points,
  field outlines, licences, pipelines, CO2 storage. Anonymous +
  queryable. **This tool wraps that tier.**
* **NDR data packages** at ndr.nstauthority.co.uk — raw SEG-Y, full
  well-log packs, mud logs, formation tops, and raw production data.
  Requires Microsoft Azure AD authentication and membership of a
  registered organisation with signed NSTA agreements. **NOT covered
  by this tool** — we can't legitimately proxy per-organisation
  licensed data. Direct NDR users go to the portal.

The Open Data tier is what NSTA has explicitly "released" from the
NDR's holdings — substantial enough for site-screening, baseline
characterisation, planning-application context. For commercial-grade
seismic interpretation or full well-log review, an NDR account is
needed.

Coverage / fields wrapped here:

* Petroleum licences (current + historic), subareas, blocks
* Hydrocarbon fields (offshore + onshore), with status + dates
* 2D + 3D seismic survey footprints from the NDR catalogue
* Subsea pipelines + point infrastructure
* CO2 storage licences, sites, complexes, appraisal-rank grid

Six layers most useful for "what NSTA-regulated activity exists at
this UK marine point?" — focused on assets that show up as polygons,
lines or points. Wellbore details we leave to BGS GeoIndex Offshore
(which republishes the NSTA hydrocarbon-well layer anyway).

Endpoint: ``services-eu1.arcgis.com/OZMfUznmLTnWccBc/...`` — public
ArcGIS REST, anonymous, NSTA Open User Licence.

Coverage: UK Continental Shelf + nearshore. Onshore points return
zero except where the offshore-tagged layers overlap into estuaries.
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

import httpx

from geo_mcp.tools._validators import validate_radius_m, validate_wgs84

_BASE = (
    "https://services-eu1.arcgis.com/OZMfUznmLTnWccBc/"
    "arcgis/rest/services"
)

# Service paths — captured April 2026 from NSTA's ArcGIS Online org.
# These differ from the display titles (some use spaces, some
# underscores, some have the (CRS) suffix). The CRS doesn't matter at
# query time — we send/receive in EPSG:4326 and the server projects.
_LAYERS: dict[str, tuple[str, str]] = {
    "hydrocarbon_fields": (
        "Offshore_hydrocarbon_fields_(WGS84)",
        "Offshore hydrocarbon fields",
    ),
    "petroleum_licences": (
        "UKCS offshore petroleum licences WGS84",
        "Offshore petroleum licences (current + historic)",
    ),
    "seismic_3d": (
        "UKCS_NDR_3D_seismic_surveys_(ED50)",
        "NDR 3D seismic surveys",
    ),
    "seismic_2d": (
        "UKCS_NDR_2D_seismic_surveys_EAB_(ED50)",
        "NDR 2D seismic surveys (line-level)",
    ),
    "pipelines": (
        "SDC_infrastructure_pipelines_(WGS84)",
        "Subsea pipelines",
    ),
    "co2_storage_licences": (
        "UKCS current carbon storage licences ED50",
        "Current CO2 storage licences",
    ),
}

_DEFAULT_RADIUS_M = 10_000      # NSTA assets are larger than BGS samples
_MAX_RADIUS_M = 100_000
_MAX_PER_LAYER = 25
_HTTP_TIMEOUT_S = 8.0
_USER_AGENT = "geomcp.dev/1.0 (+https://geomcp.dev)"

_ATTRIBUTION = (
    "Contains NSTA Open Data © Crown copyright. Sourced from the "
    "North Sea Transition Authority's public ArcGIS Open Data "
    "catalogue under the NSTA Open User Licence. The NDR (National "
    "Data Repository) layers covered here are anonymous + queryable; "
    "richer well/seismic data packages are available with free "
    "registration at ndr.nstauthority.co.uk."
)

log = logging.getLogger(__name__)


async def marine_nsta_uk(
    lat: float,
    lon: float,
    radius_m: int = _DEFAULT_RADIUS_M,
) -> dict[str, Any]:
    """Find NSTA-regulated petroleum + CO2 storage assets near a UK
    marine point.

    Queries six NSTA Open Data feature services in parallel and
    returns matched features grouped by asset class:

    - **hydrocarbon_fields** — offshore oil + gas field outlines, with
      status (PRODUCING / PRODUCTION CEASED / etc.), discovery year,
      discovery well.
    - **petroleum_licences** — offshore petroleum licences, with
      number, type (Exploration / Production / etc.), status, dates.
    - **seismic_3d** — 3D seismic survey footprints from the NDR
      catalogue.
    - **seismic_2d** — 2D seismic survey lines from the NDR catalogue.
    - **pipelines** — subsea pipelines, with diameter, product
      transported, operator.
    - **co2_storage_licences** — currently-issued CO2 storage
      licences, with operator, partners, area.

    Each list is capped at 25 features. Per-layer failures degrade
    gracefully via a ``warnings`` array — one slow upstream doesn't
    fail the whole composite.

    Coverage: UK Continental Shelf + nearshore waters. Onshore
    queries generally return zero (England onshore petroleum has its
    own layers, not included here).

    Arguments:
        lat: WGS84 latitude, -90..90.
        lon: WGS84 longitude, -180..180.
        radius_m: search radius in metres, default 10000, capped at 100000.

    Returns:
        {
          "center": {"lat", "lon", "radius_m"},
          "totals": {"<class>": int, ...},
          "hydrocarbon_fields":   [...],
          "petroleum_licences":   [...],
          "seismic_3d":           [...],
          "seismic_2d":           [...],
          "pipelines":            [...],
          "co2_storage_licences": [...],
          "source": "NSTA Open Data — UKCS petroleum + CO2 storage",
          "attribution": "..."
        }

    On invalid input returns ``{"error": ..., "message": ...}``.
    """
    err = validate_wgs84(lat, lon) or validate_radius_m(radius_m, max_m=_MAX_RADIUS_M)
    if err is not None:
        return err

    async with httpx.AsyncClient(
        timeout=_HTTP_TIMEOUT_S,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        results = await asyncio.gather(
            *(
                _query_layer(client, path, lon, lat, radius_m)
                for path, _ in _LAYERS.values()
            ),
            return_exceptions=False,
        )

    warnings: list[str] = []
    out: dict[str, Any] = {
        "center": {"lat": lat, "lon": lon, "radius_m": radius_m},
    }
    formatters = {
        "hydrocarbon_fields": _row_field,
        "petroleum_licences": _row_licence,
        "seismic_3d": _row_seismic_3d,
        "seismic_2d": _row_seismic_2d,
        "pipelines": _row_pipeline,
        "co2_storage_licences": _row_co2_licence,
    }

    totals: dict[str, int] = {}
    for (key, _meta), raw in zip(_LAYERS.items(), results):
        rows = _process(raw, formatters[key], warnings, key)
        out[key] = rows[:_MAX_PER_LAYER]
        totals[key] = len(rows)

    out["totals"] = totals
    out["source"] = "NSTA Open Data — UKCS petroleum + CO2 storage"
    out["attribution"] = _ATTRIBUTION
    if warnings:
        out["warnings"] = warnings
    return out


# ---------------------------------------------------------------------------
# Per-layer query
# ---------------------------------------------------------------------------


async def _query_layer(
    client: httpx.AsyncClient,
    service_path: str,
    lon: float, lat: float, radius_m: int,
) -> dict[str, Any] | Exception:
    """Spatial query against one NSTA feature service. Returns the raw
    ArcGIS JSON response or the exception (surfaced as a warning)."""
    # ArcGIS REST handles spaces fine if we pass the path through
    # httpx's URL builder — let it encode.
    url = f"{_BASE}/{service_path}/FeatureServer/0/query"
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "outSR": "4326",
        "distance": str(radius_m),
        "units": "esriSRUnit_Meter",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "false",
        "resultRecordCount": "100",
        "f": "json",
    }
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        log.warning("NSTA layer %s query failed: %s", service_path, exc)
        return exc


def _process(
    raw: Any,
    row_fn,
    warnings: list[str],
    layer_name: str,
) -> list[dict[str, Any]]:
    if isinstance(raw, Exception):
        warnings.append(f"{layer_name}: upstream unavailable ({type(raw).__name__})")
        return []
    err = (raw or {}).get("error") if isinstance(raw, dict) else None
    if err:
        warnings.append(f"{layer_name}: ArcGIS error {err.get('code')}: {err.get('message')}")
        return []
    feats = (raw or {}).get("features") or []
    return [row_fn(f.get("attributes") or {}) for f in feats]


# ---------------------------------------------------------------------------
# Row formatters — pick the fields most useful for an LLM agent's brief
# ---------------------------------------------------------------------------


def _row_field(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "field_name": a.get("FIELDNAME") or a.get("NAME_SHORT"),
        "field_type": a.get("FIELDTYPE"),  # GAS / OIL / GAS-CONDENSATE / etc.
        "status": a.get("STATUS"),         # PRODUCING / PRODUCTION CEASED / etc.
        "discovery_date": a.get("DISC_DATE"),
        "discovery_well": a.get("DISC_WELL"),
        "operator": a.get("OPERATOR") or a.get("CURRENT_OPERATOR"),
    }


def _row_licence(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "licence_ref": a.get("LICREF"),
        "licence_no": a.get("LICNO"),
        "licence_type": a.get("LICTYPE"),  # Production / Exploration / etc.
        "status": a.get("LICSTATUS"),
        "location": a.get("LOCATION"),
        "operator": a.get("OPERATOR") or a.get("LICENCEE"),
        "round": a.get("ROUNDNO") or a.get("RNDNO"),
        "grant_date": _epoch_or_none(a.get("GRANTDATE") or a.get("LICEFFDATE")),
        "expiry_date": _epoch_or_none(a.get("LICEXPDATE") or a.get("EXPDATE")),
    }


def _row_seismic_3d(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "survey_id": a.get("SURVEYID"),
        "survey_name": a.get("SURVEYNAME"),
        "cs9_name": a.get("CS9_NAME"),
        "survey_type": a.get("SURVEYTYPE"),
        "environment": a.get("SURVEY_ENV"),
        "record_length_s": _num_or_none(a.get("REC_LENGTH")),
        "year": _epoch_year(a.get("RECENTERED")),
    }


def _row_seismic_2d(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "survey_id": a.get("SURVEYID"),
        "line_id": a.get("LINEID"),
        "survey_name": a.get("SURVEYNAME"),
        "line_name": a.get("LINE_NAME"),
        "cs9_name": a.get("CS9_NAME"),
        "start_sp": a.get("START_SP"),
        "end_sp": a.get("END_SP"),
    }


def _row_pipeline(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "pipeline_no": a.get("PLNO") or a.get("PIPELINE_NO"),
        "name": a.get("NAME") or a.get("PLNAME"),
        "operator": a.get("OPERATOR"),
        "diameter_inch": _num_or_none(a.get("DIAMETER")),
        "product": a.get("PRODUCT"),
        "status": a.get("STATUS"),
        "from_facility": a.get("FROM_FAC") or a.get("FROMNAME"),
        "to_facility": a.get("TO_FAC") or a.get("TONAME"),
    }


def _row_co2_licence(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "licence_ref": a.get("LICREF"),
        "round": a.get("RNDNO"),
        "operator": a.get("EXPLO_OPR"),
        "partners": [
            v for v in (
                a.get("PART_ORG_1"), a.get("PART_ORG_2"),
                a.get("PART_ORG_3"), a.get("PART_ORG_4"),
            ) if v and v.strip()
        ],
        "area_km2": _num_or_none(a.get("AREA_KM2") or a.get("LIC_AREA")),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _num_or_none(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _epoch_or_none(v: Any) -> str | None:
    """ArcGIS epoch-millis → YYYY-MM-DD."""
    if v is None or v == "":
        return None
    try:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(int(v) / 1000.0, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        return None


def _epoch_year(v: Any) -> int | None:
    """ArcGIS epoch-millis → year only (compact for survey vintage)."""
    iso = _epoch_or_none(v)
    return int(iso[:4]) if iso else None
