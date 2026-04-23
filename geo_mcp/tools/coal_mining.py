"""Coal Authority mining risk lookup — live WMS GetFeatureInfo.

The Coal Authority's planning-constraints layers are distributed as
view-only WMS services (under EIR, not bulk-redistributable OGLv3),
so we query them live per request rather than ingesting polygons.
Same pattern as surface_water_risk_uk against the EA RoFSW WMS.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from geo_mcp.data_access.projections import to_osgb
from geo_mcp.tools._validators import validate_wgs84

log = logging.getLogger("geo_mcp.tools.coal_mining")

_WMS_URL = (
    "https://map.bgs.ac.uk/arcgis/services/CoalAuthority/"
    "coalauthority_planning_policy_constraints/MapServer/WMSServer"
)

# The four layers exposed on the planning-and-policy-constraints WMS,
# in the order we care about them. Order matters for `signals` output:
# reporting-area is the broadest (coalfield footprint), the others are
# progressively more specific.
_LAYERS: list[tuple[str, str]] = [
    ("Coal.Mining.Reporting.Area",
     "coal_mining_reporting_area"),
    ("Development.High.Risk.Area",
     "development_high_risk_area"),
    ("Surface.Mining.Past.and.Current",
     "surface_mining_past_or_current"),
    ("Surface.Coal.Resource.Areas",
     "surface_coal_resource_area"),
]

_ATTRIBUTION = (
    "Contains Coal Authority data © Coal Authority (now Mining Remediation "
    "Authority), made available via BGS under Open Government Licence v3.0. "
    "Sourced live from the Coal Authority Planning & Policy Constraints WMS; "
    "layer detail is restricted to the 1:10,000–1:25,000 scale range and "
    "should not be used as a substitute for a formal CON29M coal mining "
    "search report."
)

_TIMEOUT = 10.0


async def coal_mining_risk_uk(lat: float, lon: float) -> dict[str, Any]:
    """Coal-mining planning / property risk for a UK point.

    Queries the Coal Authority's Planning & Policy Constraints WMS live
    for four overlapping layers at the given point:

      * **Coal Mining Reporting Area** — the coalfield footprint. If a
        point is outside this, the Coal Authority wouldn't expect a
        mining search to be needed.
      * **Development High Risk Area** — the planning-constraint
        polygon. New development in this zone requires a Coal Mining
        Risk Assessment before the LPA can approve.
      * **Surface Mining Past & Current** — extents of opencast
        workings (historical or live). Specific hazard indicator.
      * **Surface Coal Resource Area** — shallow coal still in the
        ground. Relevant to future mineral safeguarding policy.

    Coverage: **Great Britain** (England, Wales, Scotland). Northern
    Ireland is governed by the Department for the Economy and is not
    present in this dataset — NI points return ``verdict: "coverage_gap"``.

    The tool returns a decision-oriented verdict rather than raw
    polygons — agents should treat it as "is a coal mining search
    indicated?" not as a replacement for one.

    Arguments:
        lat, lon: WGS84.

    Returns:
        {
          "point": {"lat", "lon", "easting", "northing"},
          "verdict": "outside_coalfield" | "coalfield_low_risk"
                   | "coalfield_high_risk" | "coverage_gap",
          "headline": "one-sentence plain-English summary",
          "narrative": "multi-sentence summary an agent can read verbatim",
          "signals": {
              "coal_mining_reporting_area":        bool,
              "development_high_risk_area":        bool,
              "surface_mining_past_or_current":    bool,
              "surface_coal_resource_area":        bool,
              "feature_details": [...per-hit attributes from WMS...]
          },
          "source": "Coal Authority (via BGS WMS)",
          "attribution": "..."
        }
    """
    err = validate_wgs84(lat, lon)
    if err is not None:
        return err

    # Very coarse NI bbox: west of 5.5°W, south of 55.3°N and north of 54°N.
    # Good enough to flag coverage_gap before hitting the WMS.
    if -8.5 < lon < -5.3 and 54.0 < lat < 55.3:
        return _coverage_gap_response(lat, lon)

    easting, northing = to_osgb().transform(lon, lat)

    # Tiny bbox around the point; the 101×101 image with (i=50, j=50)
    # means we're effectively sampling at the centre.
    bbox = (easting - 10, northing - 10, easting + 10, northing + 10)

    try:
        hits = await asyncio.gather(*[
            _probe_layer(wms_name, key, bbox) for (wms_name, key) in _LAYERS
        ])
    except Exception:
        log.exception("coal_mining WMS probe failed")
        return {
            "error": "upstream_unavailable",
            "message": "Coal Authority WMS could not be reached.",
        }

    signals: dict[str, Any] = {"feature_details": []}
    for (_, key), (present, details) in zip(_LAYERS, hits):
        signals[key] = present
        for d in details:
            signals["feature_details"].append({"layer": key, **d})

    verdict, headline, narrative = _verdict(signals)

    return {
        "point": {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "easting": round(easting, 2),
            "northing": round(northing, 2),
        },
        "verdict": verdict,
        "headline": headline,
        "narrative": narrative,
        "signals": signals,
        "source": "Coal Authority (via BGS WMS)",
        "attribution": _ATTRIBUTION,
    }


async def _probe_layer(
    wms_name: str,
    key: str,
    bbox: tuple[float, float, float, float],
) -> tuple[bool, list[dict[str, Any]]]:
    params = {
        "service": "WMS",
        "version": "1.3.0",
        "request": "GetFeatureInfo",
        "layers": wms_name,
        "query_layers": wms_name,
        "crs": "EPSG:27700",
        "bbox": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
        "width": "101",
        "height": "101",
        "i": "50",
        "j": "50",
        "info_format": "text/xml",
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(_WMS_URL, params=params)
    r.raise_for_status()
    text = r.text

    # The ArcGIS WMS wraps hits in <FIELDS attr1="..." attr2="..."></FIELDS>.
    # Zero hits = no FIELDS tags. Match either `<FIELDS attrs>` or
    # `<FIELDS attrs />` and capture the attribute chunk.
    feature_blocks = re.findall(r"<FIELDS\b([^>]*?)\s*/?>", text)
    details = [_parse_fields(block) for block in feature_blocks]
    return (bool(feature_blocks), details)


def _parse_fields(block: str) -> dict[str, Any]:
    """Extract attribute name/value pairs from a WMS FIELDS element body."""
    attrs: dict[str, Any] = {}
    for m in re.finditer(r'(\w+)="([^"]*)"', block):
        k, v = m.group(1), m.group(2)
        # Drop shape-internal plumbing the caller doesn't need.
        if k in ("OBJECTID", "Shape", "SHAPE_Length", "SHAPE_Area"):
            continue
        attrs[k.lower()] = v
    return attrs


def _verdict(signals: dict[str, Any]) -> tuple[str, str, str]:
    in_coalfield = signals["coal_mining_reporting_area"]
    high_risk = signals["development_high_risk_area"]
    past_surface = signals["surface_mining_past_or_current"]
    on_resource = signals["surface_coal_resource_area"]

    if not in_coalfield:
        return (
            "outside_coalfield",
            "Not in a Coal Authority reporting area — coal mining search not indicated.",
            "This point sits outside the Coal Authority's coal mining "
            "reporting footprint. A CON29M coal mining search would not "
            "typically be required here on coal-mining grounds.",
        )

    if high_risk or past_surface:
        bits: list[str] = []
        if high_risk:
            bits.append("a Coal Authority Development High Risk Area")
        if past_surface:
            bits.append("a past or current surface-mining (opencast) footprint")
        where = " and ".join(bits)
        extra = " It also sits on a Surface Coal Resource Area." if on_resource else ""
        return (
            "coalfield_high_risk",
            "Coal mining risk: specific hazard indicated — formal search recommended.",
            f"This point falls within {where}. "
            f"A CON29M coal mining search is strongly indicated; any new "
            f"development on this site will need a Coal Mining Risk "
            f"Assessment before the local planning authority can approve.{extra}",
        )

    resource_line = (
        " It lies over a Surface Coal Resource Area — relevant to mineral "
        "safeguarding, but not a present-day structural hazard."
        if on_resource else ""
    )
    return (
        "coalfield_low_risk",
        "Inside the coalfield, but no specific high-risk mining feature at this point.",
        ("This point is inside the Coal Authority's reporting area but "
         "outside any specific high-risk mining polygon. A coal mining "
         "search is still usually commissioned for conveyancing on "
         "coalfield properties — it'll be much cheaper than finding out "
         "there's an issue after the fact." + resource_line),
    )


def _coverage_gap_response(lat: float, lon: float) -> dict[str, Any]:
    return {
        "point": {"lat": round(lat, 6), "lon": round(lon, 6)},
        "verdict": "coverage_gap",
        "headline": "Coal Authority data covers Great Britain only.",
        "narrative": (
            "The Coal Authority dataset covers England, Wales, and Scotland. "
            "For Northern Ireland, mining-related property queries go via "
            "the Department for the Economy's Minerals & Petroleum Branch."
        ),
        "signals": {},
        "source": "Coal Authority (via BGS WMS)",
        "attribution": _ATTRIBUTION,
    }
