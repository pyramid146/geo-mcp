"""Flood Re eligibility as a rules-based tool.

Flood Re is the UK-wide reinsurance scheme (ABI + government) that
subsidises flood cover for higher-risk homes. Insurers pass eligible
policies into the pool; the pool caps claims so retail premiums stay
affordable.

Eligibility is defined by Flood Re's own rules and comes down to
binary tests against property attributes. We can't check a property
definitively because those attributes (build year, council tax band,
tenure, use) aren't in any of our datasets — but we can reliably
evaluate the rules if the caller provides them, and explicitly flag
which inputs are missing when they're not.
"""
from __future__ import annotations

from typing import Any, Literal

_ATTRIBUTION = (
    "Flood Re eligibility rules sourced from Flood Re's published policy "
    "at floodre.co.uk/about-flood-re/flood-re-eligibility. This tool "
    "applies the rules to caller-supplied property attributes; it is not "
    "an authoritative eligibility decision — that rests with the insurer "
    "at quote time."
)

# Canonical published rule set as of 2026-04. Keeping as explicit data
# so the docstring is searchable and the logic is auditable.
_RULES_SUMMARY = (
    "Core inclusion rules:\n"
    "  - Residential property used for dwelling purposes\n"
    "  - Built on or before 31 December 2008 (date of first ownership)\n"
    "  - Insured in the name of the individual owner or leaseholder\n"
    "  - In England, Scotland, Wales or Northern Ireland\n\n"
    "Core exclusions:\n"
    "  - Commercial / business premises\n"
    "  - Properties first occupied after 31 Dec 2008 (new-build exclusion)\n"
    "  - Blocks of flats of more than three flats on a commercial policy\n"
    "  - Buy-to-let on a commercial landlord policy (BTL residential OK in principle)\n"
    "  - Holiday lets and second homes: included only if the policy is in a\n"
    "    personal name and covers a dwelling\n"
    "  - Council tax Band H (England/Wales) or equivalent (Scotland I,\n"
    "    NI Capital Value > £750k) is NOT excluded — ignore older guidance\n"
    "    that suggested otherwise; this was removed in 2024.\n"
)


Country = Literal["England", "Scotland", "Wales", "Northern Ireland"]
PropertyType = Literal["residential", "commercial", "mixed_use"]
Tenure = Literal["owner_occupied", "rented", "leasehold", "freehold", "unknown"]


async def flood_re_eligibility_uk(
    country: str | None = None,
    property_type: str | None = None,
    build_year: int | None = None,
    flats_in_block: int | None = None,
    tenure: str | None = None,
    commercial_policy: bool | None = None,
) -> dict[str, Any]:
    """Evaluate Flood Re eligibility from caller-supplied property attributes.

    Flood Re is the UK reinsurance scheme that lets insurers offer
    affordable flood cover on higher-risk homes. Whether a specific
    property qualifies is a simple rules check once you know its
    attributes — but those attributes aren't in any open dataset
    (build year, tenure, policy type are all in private records), so
    this tool **needs the caller** to provide them.

    Pass in what's known; the response tells you:
      * whether the property is **likely eligible**, **ineligible**,
        or the inputs are **insufficient** to decide;
      * which specific rule drove the answer;
      * which inputs, if any, are still missing.

    Typical chain: agent gets a lat/lon from a user → calls
    ``flood_risk_probability_uk`` to see if Flood Re cover matters →
    asks the user for the property attributes → calls this tool.

    Arguments (all optional):
        country: ``"England" | "Scotland" | "Wales" | "Northern Ireland"``.
        property_type: ``"residential" | "commercial" | "mixed_use"``.
        build_year: year of first occupation (int). Anything > 2008 is excluded.
        flats_in_block: number of flats if the property is in a block of flats.
            Blocks of >3 flats on a commercial policy are excluded.
        tenure: ``"owner_occupied" | "rented" | "leasehold" | "freehold"``.
        commercial_policy: ``true`` if the cover is under a commercial/landlord policy.

    Returns:
        {
          "eligible": "likely_eligible" | "ineligible" | "insufficient_information",
          "reasons": [<rule names that applied>],
          "missing_inputs": [<field names the caller didn't supply>],
          "rules_applied": "<summary text>",
          "rules_version": "2026-04",
          "source": "Flood Re published rules",
          "attribution": "..."
        }
    """
    reasons: list[str] = []
    missing: list[str] = []

    if country is None:
        missing.append("country")
    elif country not in ("England", "Scotland", "Wales", "Northern Ireland"):
        return {
            "error": "invalid_country",
            "message": f"country must be one of England/Scotland/Wales/Northern Ireland, got {country!r}.",
        }

    if property_type is None:
        missing.append("property_type")
    elif property_type == "commercial":
        return _ineligible("property_type_is_commercial", missing)

    if build_year is None:
        missing.append("build_year")
    elif build_year > 2008:
        return _ineligible("built_after_31_december_2008", missing)
    elif build_year < 1800:
        reasons.append("very_old_build_accepted")  # no explicit age-lower exclusion

    if flats_in_block is not None and flats_in_block > 3 and commercial_policy:
        return _ineligible("block_of_more_than_three_flats_on_commercial_policy", missing)

    if commercial_policy is True and tenure == "rented":
        return _ineligible("commercial_landlord_policy", missing)

    if missing:
        return {
            "eligible": "insufficient_information",
            "reasons": reasons,
            "missing_inputs": missing,
            "guidance": (
                "Supply the missing inputs to get a firm likely/ineligible read. "
                "Final eligibility is decided by the insurer at quote time."
            ),
            "rules_applied": _RULES_SUMMARY,
            "rules_version": "2026-04",
            "source": "Flood Re published rules",
            "attribution": _ATTRIBUTION,
        }

    reasons.append("residential_dwelling_built_on_or_before_2008")
    return {
        "eligible": "likely_eligible",
        "reasons": reasons,
        "missing_inputs": [],
        "guidance": (
            "This property looks eligible on the published rules. The insurer "
            "makes the final decision at quote time — some insurers don't use "
            "Flood Re at all, so 'eligible' doesn't guarantee every quote cites it."
        ),
        "rules_applied": _RULES_SUMMARY,
        "rules_version": "2026-04",
        "source": "Flood Re published rules",
        "attribution": _ATTRIBUTION,
    }


def _ineligible(rule: str, missing: list[str]) -> dict[str, Any]:
    return {
        "eligible": "ineligible",
        "reasons": [rule],
        "missing_inputs": missing,
        "rules_applied": _RULES_SUMMARY,
        "rules_version": "2026-04",
        "source": "Flood Re published rules",
        "attribution": _ATTRIBUTION,
    }
