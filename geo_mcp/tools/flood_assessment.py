"""Composite homeowner-grade flood assessment.

Orchestrates the per-source flood tools into a single call that a
property agent / conveyancer / insurance workflow can invoke and
get a coherent answer from. Deliberately the opposite of the
single-source tools: this one synthesises *across* datasets to
produce a decision-oriented narrative.
"""
from __future__ import annotations

import asyncio
from typing import Any

from geo_mcp.tools._validators import is_valid_uk_postcode
from geo_mcp.tools.flood import flood_risk_uk
from geo_mcp.tools.flood_historic import historic_floods_uk
from geo_mcp.tools.flood_planning import nppf_planning_context_uk
from geo_mcp.tools.flood_probability import flood_risk_probability_uk
from geo_mcp.tools.flood_surface_water import surface_water_risk_uk
from geo_mcp.tools.geocoding import reverse_geocode_uk

_ATTRIBUTION = (
    "Composite view built from multiple Environment Agency and ONS datasets — see "
    "each sub-source block for its own attribution text. All underlying data is "
    "OGLv3-licensed."
)


async def flood_assessment_uk(
    postcode: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> dict[str, Any]:
    """Full flood-risk picture for a UK location — the single-call answer for a property report.

    Accepts **either** a postcode **or** a WGS84 lat/lon. If a postcode
    is given, we reverse-geocode it internally to get a point. Returns a
    consolidated view covering the four signals a homeowner /
    conveyancer / insurer actually want together:

      1. **Planning zone** (Flood Map for Planning, ignores defences)
         — from ``flood_risk_uk``. NPPF sequential-test basis.
      2. **Probabilistic risk** (RoFRS, accounts for defences)
         — from ``flood_risk_probability_uk``, postcode-grain.
      3. **Surface water risk** (RoFSW)
         — from ``surface_water_risk_uk``.
      4. **Historic flooding** (actual recorded events since 1946)
         — from ``historic_floods_uk``.

    Also folds in:
      * NPPF planning context for a 'more_vulnerable' use (dwellinghouse)
        — the sequential/exception test status a planner cares about.
      * A summary verdict and plain-English narrative suitable for an
        agent to read back verbatim.

    Coverage is **England only** across all four signals. For Welsh,
    Scottish, NI, or Crown-Dependency addresses this tool returns
    ``verdict: "coverage_gap"`` and an honest "go elsewhere" narrative —
    no silent false-negative "low risk" dressed up as a clean answer.

    Verdict thresholds (when the point is in-coverage):
      - ``high``     — Flood Zone 3, OR RoFRS high-band, OR surface
                       water High, OR a historic flood since 1990,
                       OR ≥2 historic floods (any date).
      - ``moderate`` — Flood Zone 2, OR RoFRS medium/low-band,
                       OR surface water Medium/Low, OR any single
                       pre-1990 historic flood.
      - ``low``      — none of the above.

    The "recent flood" cutoff matters: a single 1947 Lower-Severn
    outline on a point that now sits in Zone 1 and has no RoFRS
    band shouldn't force a "high" verdict decades after the event.

    Arguments (provide exactly one of):
        postcode: UK postcode, spaced or unspaced, case-insensitive.
        lat, lon: WGS84 coordinates.

    Returns:
        {
          "verdict": "low" | "moderate" | "high" | "coverage_gap",
          "headline": "one-sentence plain-English summary",
          "narrative": "multi-sentence summary an agent can read verbatim",
          "site": { "postcode"?, "lat", "lon", "admin"? },
          "signals": {
              "planning_zone":      {...from flood_risk_uk},
              "probability_rofrs":  {...from flood_risk_probability_uk | null},
              "surface_water":      {...from surface_water_risk_uk},
              "historic":           {...from historic_floods_uk},
              "nppf_planning":      {...from nppf_planning_context_uk}
          },
          "attribution": "...",
        }
    """
    have_postcode = bool(postcode and postcode.strip())
    have_coords = (lat is not None) and (lon is not None)
    if have_postcode == have_coords:
        return {
            "error": "invalid_input",
            "message": "Provide exactly one of: postcode, or both lat and lon.",
        }

    # Resolve to (lat, lon, postcode, admin) via reverse_geocode_uk when we
    # have coords, or via a geocode_uk-style postcode lookup when we have a
    # postcode. Reverse geocode also gives us the postcode back, which the
    # RoFRS tool needs.
    site_postcode: str | None = None
    if have_coords:
        rg = await reverse_geocode_uk(lat=lat, lon=lon)
        if "error" in rg:
            return {"error": "lookup_failed", "message": rg.get("message"), "upstream": rg}
        site_postcode = rg["postcode"]
        admin = rg.get("admin")
    else:
        q = (postcode or "").strip().upper()
        if not is_valid_uk_postcode(q):
            return {"error": "invalid_postcode", "message": f"{postcode!r} is not a UK postcode."}
        # Geocode the postcode to a lat/lon via a minimal ONSPD lookup
        from geo_mcp.tools.forward_geocoding import geocode_uk
        g = await geocode_uk(query=q)
        if g.get("match_type") != "postcode":
            return {
                "error": "postcode_not_found",
                "message": f"Postcode {q!r} not found in ONSPD.",
                "upstream": g,
            }
        lat, lon = g["lat"], g["lon"]
        site_postcode = g["context"]["postcode"]
        rg = await reverse_geocode_uk(lat=lat, lon=lon)
        admin = rg.get("admin") if "error" not in rg else None

    # Fire the per-signal tools in parallel. They're fully independent —
    # each queries a different dataset or upstream — so the total latency
    # is `max(subtool latency)` rather than `sum`. Surface water is the
    # slowest (~500 ms live EA WMS); the others are DB lookups.
    # asyncio.gather raises if any sub-task raises, but these tools
    # return structured error dicts instead of raising, so gather is safe.
    rofrs_task = (
        flood_risk_probability_uk(postcode=site_postcode)
        if site_postcode else asyncio.sleep(0, result=None)
    )
    zone, rofrs, surface, historic, nppf = await asyncio.gather(
        flood_risk_uk(lat=lat, lon=lon),
        rofrs_task,
        surface_water_risk_uk(lat=lat, lon=lon),
        historic_floods_uk(lat=lat, lon=lon),
        nppf_planning_context_uk(lat=lat, lon=lon, proposed_vulnerability="more_vulnerable"),
    )

    # Derive an overall verdict. "High" if any one of:
    #   - Flood Zone 3
    #   - RoFRS worst_band = High
    # If we're outside the dataset coverage (Wales / Scotland / NI /
    # Crown Dependencies) every flood signal is silently null-ish,
    # which would look misleadingly like "no risk". Detect and return
    # coverage_gap instead.
    ctry_code = (admin or {}).get("country", {}).get("code") if admin else None
    country_covered = ctry_code == "E92000001"
    # `flood_risk_uk` may itself return verdict=coverage_gap when the
    # point is outside England; use that as a second signal in case the
    # reverse-geocode didn't resolve an admin country code.
    zone_gap = (zone or {}).get("verdict") == "coverage_gap"
    if zone_gap or (ctry_code is not None and not country_covered):
        verdict = "coverage_gap"
    else:
        planning_zone = int(zone.get("zone") or 1)
        rofrs_worst = (rofrs or {}).get("worst_band")
        surface_band = surface.get("band", "Very Low")
        historic_count = historic.get("count", 0)
        historic_most_recent = (historic or {}).get("most_recent")  # "YYYY-MM-DD" | null

        # A recorded historic flood pushes the verdict up only when it's
        # *recent* or *frequent* — a single 1947 Lower-Severn outline on
        # a point that now sits outside every planning zone shouldn't be
        # enough to tag a property "high" and scare a buyer off.
        recent_threshold = "1990-01-01"
        historic_recent = (historic_most_recent or "") >= recent_threshold
        historic_high_signal = (historic_count >= 2) or historic_recent
        historic_any = historic_count > 0

        high_markers = (
            planning_zone == 3
            or rofrs_worst == "high"
            or surface_band == "High"
            or historic_high_signal
        )
        moderate_markers = (
            planning_zone == 2
            or rofrs_worst in ("medium", "low")
            or surface_band in ("Medium", "Low")
            or historic_any
        )
        if high_markers:
            verdict = "high"
        elif moderate_markers:
            verdict = "moderate"
        else:
            verdict = "low"

    if verdict == "coverage_gap":
        country_label = (admin or {}).get("country", {}).get("name") or "this country"
        headline = (
            f"Data coverage gap — these flood tools are England-only; "
            f"{country_label} needs nation-specific sources."
        )
        narrative = (
            f"The EA flood tools (planning zones, RoFRS, surface water, "
            f"recorded floods) all cover England only. This location resolves to "
            f"{country_label}, so the signals above are coverage gaps rather "
            f"than assessments. Use Natural Resources Wales / SEPA / DAERA for "
            f"the relevant nation."
        )
    else:
        headline, narrative = _narrative(
            verdict=verdict,
            postcode=site_postcode,
            zone=planning_zone,
            rofrs=rofrs,
            surface_band=surface_band,
            historic=historic,
            nppf=nppf,
        )

    return {
        "verdict": verdict,
        "headline": headline,
        "narrative": narrative,
        "site": {
            "postcode": site_postcode,
            "lat": lat,
            "lon": lon,
            "admin": admin,
        },
        "signals": {
            "planning_zone":     zone,
            "probability_rofrs": rofrs,
            "surface_water":     surface,
            "historic":          historic,
            "nppf_planning":     nppf,
        },
        "attribution": _ATTRIBUTION,
    }


def _narrative(
    *,
    verdict: str,
    postcode: str | None,
    zone: int,
    rofrs: dict[str, Any] | None,
    surface_band: str,
    historic: dict[str, Any],
    nppf: dict[str, Any],
) -> tuple[str, str]:
    loc = f"postcode {postcode}" if postcode else "this location"

    zone_phrase = {
        1: f"{loc} is in Flood Zone 1 — the lowest planning zone for rivers and sea",
        2: f"{loc} is in Flood Zone 2 (0.1–1% annual probability from rivers)",
        3: f"{loc} is in Flood Zone 3 (≥1% annual probability from rivers or ≥0.5% from the sea)",
    }[zone]

    rofrs_phrase = ""
    if rofrs and rofrs.get("risk_identified"):
        band = rofrs.get("worst_band", "unknown")
        band_txt = "High" if band == "high" else ("Medium" if band == "medium" else band.replace("_", " ").title())
        res_high = (rofrs.get("by_band", {}).get("high", {}) or {}).get("residential", 0)
        rofrs_phrase = (
            f" RoFRS (which accounts for flood defences) rates this postcode at **{band_txt}**"
            + (f", with {res_high} residential properties classed as High-risk" if res_high else "")
            + "."
        )
    elif rofrs is not None:
        rofrs_phrase = " RoFRS has not flagged any properties here as at-risk from rivers or sea."

    surface_phrase = ""
    if surface_band in ("Low", "Medium", "High"):
        surface_phrase = f" Surface-water risk is **{surface_band}** — pluvial flooding is an independent source and can affect properties well away from rivers."
    elif surface_band == "Very Low":
        surface_phrase = " No mapped surface-water flood risk at this point."

    historic_phrase = ""
    hc = historic.get("count", 0)
    if hc == 0:
        historic_phrase = " No recorded historical floods at this exact location."
    else:
        most_recent = historic.get("most_recent")
        historic_phrase = (
            f" The EA has **{hc} recorded historical flood**"
            + ("s" if hc != 1 else "")
            + (f" at this location, most recently in {most_recent}" if most_recent else "")
            + "."
        )

    planning_phrase = ""
    if nppf.get("sequential_test_required"):
        planning_phrase = (
            f" For planning, a new dwelling here would require the NPPF "
            f"Sequential Test"
            + (" and an Exception Test" if nppf.get("exception_test_required") else "")
            + "; commission a Flood Risk Assessment before applying."
        )

    headline_map = {
        "low":          "Low overall flood risk.",
        "moderate":     "Moderate flood risk — check specifics before proceeding.",
        "high":         "Elevated flood risk — investigate insurance and planning implications before proceeding.",
        "unknown":      "Unable to give a flood verdict from available data.",
        "coverage_gap": "Data coverage gap — flood tools are England-only.",
    }
    headline = headline_map[verdict]

    narrative = zone_phrase + "." + rofrs_phrase + surface_phrase + historic_phrase + planning_phrase
    return headline, narrative
