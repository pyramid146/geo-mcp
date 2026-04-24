"""Energy Performance Certificate lookup.

One tool, two modes: postcode-wide summary (every property with a
lodged EPC in the postcode) or property-specific lookup by UPRN
(latest lodged EPC for that specific unit). Both return enough
signal to drive Flood Re eligibility (the EPC build-age-band), a
retrofit / climate conversation (rating + efficiency + fuel), and
a conveyancer's "is this energy-efficient" check.
"""
from __future__ import annotations

from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._validators import canonical_spaced_postcode, is_valid_uk_postcode

_ATTRIBUTION = (
    "Contains Energy Performance Certificate data © Crown copyright. "
    "Licensed under the Open Government Licence v3.0. Published via the "
    "Ministry of Housing, Communities & Local Government (MHCLG) "
    "'Get energy performance of buildings data' service."
)

# Interpretation of construction_age_band relative to the Flood Re
# pre-2009 cutoff. Values keyed on the band strings EPC emits.
# - "pre_2009": built on or before 31 Dec 2008 → eligible by year
# - "post_2008": built 2009 or later → ineligible by year
# - "spans_cutoff": band straddles 2008/2009 → cannot tell without more
# - None for missing / unknown
def _flood_re_year_signal(age_band: str | None) -> str | None:
    if not age_band or not age_band.strip():
        return None
    b = age_band.strip().upper()
    if "BEFORE 1900" in b:
        return "pre_2009"
    # Well-defined pre-2009 bands
    for pre in (
        "1900-1929", "1930-1949", "1950-1966", "1967-1975", "1976-1982",
        "1983-1990", "1991-1995", "1996-2002", "2003-2006",
    ):
        if pre in b:
            return "pre_2009"
    if "2012 ONWARDS" in b:
        return "post_2008"
    if "2007 ONWARDS" in b or "2007-2011" in b:
        return "spans_cutoff"
    if "NO DATA" in b or "INVALID" in b:
        return None
    return None


def _property_block(row) -> dict[str, Any]:
    age_band = row.get("construction_age_band") or None
    return {
        "address": row.get("address"),
        "uprn": row.get("uprn") or None,
        "postcode": row.get("postcode"),
        "property_type": row.get("property_type") or None,
        "built_form": row.get("built_form") or None,
        "construction_age_band": age_band,
        "flood_re_year_signal": _flood_re_year_signal(age_band),
        "tenure": row.get("tenure") or None,
        "transaction_type": row.get("transaction_type") or None,
        "main_fuel": row.get("main_fuel") or None,
        "total_floor_area_sqm": _float(row.get("total_floor_area")),
        "habitable_rooms": _int(row.get("number_habitable_rooms")),
        "energy_rating": {
            "current": row.get("current_energy_rating") or None,
            "potential": row.get("potential_energy_rating") or None,
            "current_score": _int(row.get("current_energy_efficiency")),
            "potential_score": _int(row.get("potential_energy_efficiency")),
        },
        "co2_emissions_current_tonnes_yr": _float(row.get("co2_emissions_current")),
        "co2_emissions_potential_tonnes_yr": _float(row.get("co2_emissions_potential")),
        "inspection_date": row.get("inspection_date") or None,
        "lodgement_date": row.get("lodgement_date") or None,
        "certificate_number": row.get("certificate_number") or None,
    }


def _int(v: Any) -> int | None:
    try:
        return int(str(v).strip()) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _float(v: Any) -> float | None:
    try:
        return round(float(str(v).strip()), 2) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


async def energy_performance_uk(
    postcode: str | None = None,
    uprn: str | None = None,
) -> dict[str, Any]:
    """Look up Energy Performance Certificates by postcode or UPRN.

    The EPC register covers every England & Wales property with a
    lodged certificate since 2008. An EPC carries the property's
    **construction age band** (the Flood Re pre-2009 signal), the
    **current and potential energy rating** (A–G), floor area,
    habitable-room count, main heating fuel, and CO₂ emissions. It's
    the single richest property-level open dataset in the UK.

    Two modes:

    * **UPRN-specific** — pass a UPRN (optionally with the postcode).
      Returns the **latest** EPC lodged for that unit.
    * **Postcode summary** — pass a postcode alone. Returns an
      aggregate view (count, rating distribution, age-band
      distribution, property-type mix, mean floor area, mean energy
      efficiency) plus up to 20 most-recently-lodged EPCs deduped to
      one-per-UPRN. Good for "what are the properties in this
      postcode like?".

    Each certificate block includes a ``flood_re_year_signal`` field
    derived from the construction age band, with values:

      - ``"pre_2009"``     — band ends 2008 or earlier → eligible by year for Flood Re
      - ``"post_2008"``    — band starts 2012 or later → ineligible by year
      - ``"spans_cutoff"`` — band is "2007 onwards" or "2007-2011" → ambiguous
      - ``null``           — missing / invalid age band

    Coverage is **England & Wales only**. A not-found result can mean
    the property has never been sold / rented since 2008 (EPC is
    triggered by those events, not by occupation).

    Arguments (provide at least ``postcode`` or ``uprn``):
        postcode: UK postcode, spaced or unspaced, case-insensitive.
        uprn: numeric Unique Property Reference Number.

    Returns on the postcode-summary path:
        {
          "postcode": "...",
          "count": int,
          "distinct_properties": int,
          "rating_distribution": {"A":..,"B":..,"C":..,"D":..,"E":..,"F":..,"G":..},
          "by_property_type": {...},
          "by_age_band": {...},
          "stats": {"mean_floor_area_sqm", "mean_current_efficiency",
                    "mean_potential_efficiency"},
          "properties": [...up to 20 latest-per-uprn, each a full
                         property block with flood_re_year_signal...],
          "source": "...", "attribution": "..."
        }

    Returns on the UPRN-specific path:
        {
          "uprn": "...",
          "property": {...single property block...},
          "source": "...", "attribution": "..."
        }

    On invalid input, returns ``{"error": ..., "message": ...}``.
    """
    if not postcode and not uprn:
        return {
            "error": "invalid_input",
            "message": "Provide at least one of postcode or uprn.",
        }

    pool = await get_pool()

    # UPRN mode: latest EPC for that unit.
    if uprn:
        uprn_s = str(uprn).strip()
        if not uprn_s.isdigit():
            return {"error": "invalid_uprn", "message": f"UPRN must be numeric, got {uprn!r}."}
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                  FROM staging.epc_domestic
                 WHERE uprn = $1
                 ORDER BY lodgement_date DESC NULLS LAST
                 LIMIT 1
                """,
                uprn_s,
            )
        if row is None:
            return {
                "uprn": uprn_s,
                "property": None,
                "note": "No EPC found for this UPRN. The property may never have been sold or let since 2008.",
                "source": "EPC Register (domestic)",
                "attribution": _ATTRIBUTION,
            }
        return {
            "uprn": uprn_s,
            "property": _property_block(dict(row)),
            "source": "EPC Register (domestic)",
            "attribution": _ATTRIBUTION,
        }

    # Postcode mode.
    q = postcode.strip() if postcode else ""
    if not is_valid_uk_postcode(q):
        return {"error": "invalid_postcode", "message": f"{postcode!r} is not a UK postcode."}
    spaced = canonical_spaced_postcode(q)

    async with pool.acquire() as conn:
        # All certificates in postcode, up to a safety cap. Dense urban
        # postcodes can carry hundreds of EPCs over the register's
        # history; fetching thousands is wasteful given we dedupe to
        # one-per-UPRN and return at most 20 to the caller anyway.
        rows = await conn.fetch(
            """
            SELECT *
              FROM staging.epc_domestic
             WHERE postcode = $1
             ORDER BY lodgement_date DESC NULLS LAST
             LIMIT 2000
            """,
            spaced,
        )

    if not rows:
        return {
            "postcode": spaced,
            "count": 0,
            "distinct_properties": 0,
            "rating_distribution": {},
            "by_property_type": {},
            "by_age_band": {},
            "stats": None,
            "properties": [],
            "note": "No EPCs lodged in this postcode.",
            "source": "EPC Register (domestic)",
            "attribution": _ATTRIBUTION,
        }

    # Dedupe to latest-per-UPRN, falling back to address when UPRN is empty.
    seen: dict[str, dict[str, Any]] = {}
    for r in rows:
        d = dict(r)
        key = d.get("uprn") or d.get("address") or d.get("certificate_number")
        if key and key not in seen:
            seen[key] = d

    # Distribution + stats from ALL certificates (not just latest), per
    # EPC convention — each certificate is a snapshot in time.
    rating_dist = {k: 0 for k in ("A", "B", "C", "D", "E", "F", "G")}
    by_type: dict[str, int] = {}
    by_age: dict[str, int] = {}
    floor_areas: list[float] = []
    eff_current: list[int] = []
    eff_potential: list[int] = []
    for r in rows:
        rating = (r.get("current_energy_rating") or "").strip().upper()
        if rating in rating_dist:
            rating_dist[rating] += 1
        ptype = r.get("property_type") or "Unknown"
        by_type[ptype] = by_type.get(ptype, 0) + 1
        age = r.get("construction_age_band") or "Unknown"
        by_age[age] = by_age.get(age, 0) + 1
        fa = _float(r.get("total_floor_area"))
        if fa is not None and fa > 0:
            floor_areas.append(fa)
        ec = _int(r.get("current_energy_efficiency"))
        if ec is not None and 0 <= ec <= 100:
            eff_current.append(ec)
        ep = _int(r.get("potential_energy_efficiency"))
        if ep is not None and 0 <= ep <= 100:
            eff_potential.append(ep)

    def _mean(xs):
        return round(sum(xs) / len(xs), 1) if xs else None

    return {
        "postcode": spaced,
        "count": len(rows),
        "distinct_properties": len(seen),
        "rating_distribution": rating_dist,
        "by_property_type": by_type,
        "by_age_band": by_age,
        "stats": {
            "mean_floor_area_sqm": _mean(floor_areas),
            "mean_current_efficiency": _mean(eff_current),
            "mean_potential_efficiency": _mean(eff_potential),
        },
        "properties": [_property_block(d) for d in list(seen.values())[:20]],
        "source": "EPC Register (domestic)",
        "attribution": _ATTRIBUTION,
    }
