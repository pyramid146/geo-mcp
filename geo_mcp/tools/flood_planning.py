"""NPPF flood-zone planning context as a rules-based overlay.

The National Planning Policy Framework (NPPF) and its Flood Risk and
Coastal Change practice guidance set out the Sequential Test and the
Exception Test that Local Planning Authorities apply to development
proposals in Flood Zones 2 and 3. This tool maps a flood zone (from
``flood_risk_uk``) plus a proposed vulnerability class to the tests
that apply and what's typically required.

The vulnerability classifications come from NPPF Table 2:
  essential_infrastructure, highly_vulnerable, more_vulnerable,
  less_vulnerable, water_compatible.
"""
from __future__ import annotations

from typing import Any, Literal

from geo_mcp.tools.flood import flood_risk_uk

_ATTRIBUTION = (
    "NPPF Flood Risk and Coastal Change planning practice guidance as "
    "published by DLUHC / MHCLG. Underlying flood zone from the EA Flood "
    "Map for Planning (OGLv3). This tool summarises published policy; "
    "it is not a planning determination — only the LPA can make those."
)

# NPPF Table 3 compatibility matrix.
# Rows = proposed use vulnerability class; cols = flood zone.
# Cells: 'permitted' | 'exception_test' | 'not_permitted'.
_COMPATIBILITY: dict[str, dict[int, str]] = {
    "essential_infrastructure": {
        1: "permitted",
        2: "permitted",
        3: "exception_test",     # and only if it has to be there
    },
    "highly_vulnerable": {
        1: "permitted",
        2: "exception_test",
        3: "not_permitted",
    },
    "more_vulnerable": {
        1: "permitted",
        2: "permitted",          # sequential test only
        3: "exception_test",
    },
    "less_vulnerable": {
        1: "permitted",
        2: "permitted",
        3: "exception_test",     # technically permitted in 3a only
    },
    "water_compatible": {
        1: "permitted",
        2: "permitted",
        3: "permitted",
    },
}

_VULNERABILITY_EXAMPLES: dict[str, str] = {
    "essential_infrastructure":
        "Transport infrastructure (motorways, railways), emergency services, "
        "telecoms and utility infrastructure that has to operate during floods.",
    "highly_vulnerable":
        "Basement dwellings, caravan sites, installations requiring hazardous "
        "substances, emergency service stations (police/fire/ambulance).",
    "more_vulnerable":
        "Hospitals, residential care homes, dwellinghouses and student halls, "
        "educational establishments.",
    "less_vulnerable":
        "Retail, commercial, industrial, non-residential health centres, "
        "leisure facilities with limited flooding risk to life.",
    "water_compatible":
        "Marinas, water-based recreation, flood-control infrastructure, "
        "sewage transmission in-line with water.",
}

Vulnerability = Literal[
    "essential_infrastructure", "highly_vulnerable", "more_vulnerable",
    "less_vulnerable", "water_compatible",
]


async def nppf_planning_context_uk(
    lat: float,
    lon: float,
    proposed_vulnerability: str | None = None,
) -> dict[str, Any]:
    """Summarise NPPF flood-zone planning requirements for a site and a proposed use.

    Takes a WGS84 point and (optionally) a proposed use's vulnerability
    classification from NPPF Table 2, looks up the flood zone, then
    returns the Sequential Test / Exception Test requirements that
    would apply under NPPF planning practice guidance.

    This is the lookup a planning consultant or a developer's agent
    would do *before* committing to a site — it tells you whether a
    proposed use is a viable candidate there at all, and what extra
    tests / assessments will likely be demanded.

    Vulnerability classes (pick the closest match for the proposed use):

      - **essential_infrastructure** — major transport, utilities
      - **highly_vulnerable**         — basements, caravan sites, hazardous stores
      - **more_vulnerable**           — homes, hospitals, care homes, schools
      - **less_vulnerable**           — shops, offices, industrial
      - **water_compatible**          — marinas, sewage treatment, flood defences

    If ``proposed_vulnerability`` is omitted, returns a matrix of
    requirements for all five classes so the caller can pick.

    Coverage: flood zone data is **England only**. For Welsh / Scottish
    sites, the tool returns ``flood_zone: 1`` by default — misleading;
    use TAN15 (Wales) or SEPA guidance (Scotland) for those.

    Arguments:
        lat, lon: WGS84 coordinates, required.
        proposed_vulnerability: one of the five class names above, optional.

    Returns:
        {
          "site": {
              "lat", "lon",
              "flood_zone": 1|2|3,
              "flood_source": str | null,          # from flood_risk_uk
          },
          "sequential_test_required": bool,
          "exception_test_required": bool | null,  # null if no proposed use given
          "compatibility": str,                    # permitted/exception_test/not_permitted
          "by_vulnerability_class": {              # when proposed_vulnerability is None
              "essential_infrastructure": str, ...
          },
          "guidance": str,
          "source": "...",
          "attribution": "..."
        }
    """
    if proposed_vulnerability is not None and proposed_vulnerability not in _COMPATIBILITY:
        return {
            "error": "invalid_vulnerability",
            "message": (
                f"proposed_vulnerability must be one of {sorted(_COMPATIBILITY)}, "
                f"got {proposed_vulnerability!r}."
            ),
        }

    zone_info = await flood_risk_uk(lat=lat, lon=lon)
    if "error" in zone_info:
        return zone_info
    zone = int(zone_info["zone"])

    site = {
        "lat": lat,
        "lon": lon,
        "flood_zone": zone,
        "flood_source": zone_info.get("source"),
    }

    # Sequential test applies to all development in Flood Zones 2 and 3.
    sequential = zone in (2, 3)

    result: dict[str, Any] = {
        "site": site,
        "sequential_test_required": sequential,
        "source": "NPPF Flood Risk and Coastal Change PPG + EA Flood Map for Planning",
        "attribution": _ATTRIBUTION,
    }

    if proposed_vulnerability is None:
        # Return the full matrix; caller can pick.
        result["by_vulnerability_class"] = {
            cls: {
                "compatibility": _COMPATIBILITY[cls][zone],
                "examples": _VULNERABILITY_EXAMPLES[cls],
            }
            for cls in _COMPATIBILITY
        }
        result["exception_test_required"] = None
        result["guidance"] = (
            f"Site is in Flood Zone {zone}. "
            + ("Sequential Test applies to all proposed development. "
               if sequential else "No Sequential Test required in Flood Zone 1. ")
            + "Supply a proposed_vulnerability class for a specific compatibility read."
        )
    else:
        compatibility = _COMPATIBILITY[proposed_vulnerability][zone]
        result["proposed_vulnerability"] = proposed_vulnerability
        result["compatibility"] = compatibility
        result["exception_test_required"] = (compatibility == "exception_test")
        result["guidance"] = _guidance(zone, proposed_vulnerability, compatibility)

    return result


def _guidance(zone: int, vuln: str, compat: str) -> str:
    if compat == "not_permitted":
        return (
            f"NPPF Table 3 does not permit '{vuln}' development in Flood Zone {zone}. "
            "An application is extremely unlikely to succeed; consider a different site."
        )
    if compat == "exception_test":
        return (
            f"'{vuln}' in Flood Zone {zone} is permitted only if both the Sequential "
            "Test and the Exception Test are passed. Expect the LPA to demand a "
            "Flood Risk Assessment, evidence that the development will be safe for "
            "its lifetime, and that it provides wider sustainability benefits that "
            "outweigh flood risk."
        )
    if zone in (2, 3):
        return (
            f"'{vuln}' is compatible with Flood Zone {zone} under Table 3, but the "
            "Sequential Test still applies — the applicant must show there are no "
            "reasonably available sites at lower flood risk."
        )
    return f"'{vuln}' is compatible with Flood Zone 1; no flood-specific NPPF tests apply."
