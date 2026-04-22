from __future__ import annotations

from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._validators import canonical_spaced_postcode, is_valid_uk_postcode

_ATTRIBUTION = (
    "Contains Environment Agency data © Environment Agency copyright and/or "
    "database right 2025. Some features based on CEH digital spatial data © NERC. "
    "Licensed under the Open Government Licence v3.0."
)

_QUERY = """
SELECT pcds,
       cntpc          AS total_properties,
       res_cntpc      AS residential,
       nrp_cntpc      AS non_residential,
       unc_cntpc      AS unclassified,
       res_cnt_high,   res_cnt_medium,   res_cnt_low,   res_cnt_verylow,
       nrp_cnt_high,   nrp_cnt_medium,   nrp_cnt_low,   nrp_cnt_verylow,
       unc_cnt_high,   unc_cnt_medium,   unc_cnt_low,   unc_cnt_verylow,
       tot_cnt_high,   tot_cnt_medium,   tot_cnt_low,   tot_cnt_verylow
  FROM staging.rofrs_postcodes
 WHERE pcds = $1;
"""


async def flood_risk_probability_uk(postcode: str) -> dict[str, Any]:
    """Probabilistic flood risk for one UK postcode, from the EA's RoFRS dataset.

    The response tells you, for the given postcode, how many properties
    fall into each of the four EA flood-likelihood bands **after** flood
    defences are taken into account. This is the dataset the EA surfaces
    through *Check Your Long Term Flood Risk* on gov.uk and the one UK
    insurers price against — complementary to ``flood_risk_uk``, which
    returns the *planning* zone for a single lat/lon and ignores defences.

    EA likelihood bands:
      - **high**       ≥3.3% annual chance
      - **medium**     1 – 3.3%
      - **low**        0.1 – 1%
      - **very_low**   <0.1%

    Accepts a postcode in any common form ("SW1A 1AA", "sw1a1aa",
    "SW1A1AA"); they're normalised to the spaced canonical form
    (``pcds``) before lookup.

    Coverage is **England only**. A postcode that isn't in the RoFRS
    dataset returns ``risk_identified: false`` — meaning the EA has
    *not* flagged any at-risk properties there. That's a clean "no
    notable river or sea flood risk" signal, but it does not say
    anything about surface water or groundwater risk (separate
    datasets). Postcodes in Scotland / Wales / NI return
    ``risk_identified: false`` for the same reason — no coverage.

    Arguments:
        postcode: the UK postcode (spaced or unspaced, case-insensitive).

    Returns one of:

      * Risk identified — full response:
        ``{postcode, risk_identified: true, worst_band,
        properties: {total, residential, non_residential, unclassified},
        by_band: {<band>: {residential, non_residential, unclassified, total}},
        source, attribution}``

      * No RoFRS entry — clean "no notable risk" signal:
        ``{postcode, risk_identified: false, note, source, attribution}``

      * Invalid input:
        ``{error: "invalid_postcode", message: ...}``
    """
    if not isinstance(postcode, str) or not postcode.strip():
        return {"error": "invalid_postcode", "message": "postcode must be a non-empty string."}
    raw = postcode.strip()
    if not is_valid_uk_postcode(raw):
        return {
            "error": "invalid_postcode",
            "message": f"{postcode!r} does not look like a UK postcode (letter+digit outward, digit+2 letters inward).",
        }

    spaced = canonical_spaced_postcode(raw)

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_QUERY, spaced)

    if row is None:
        return {
            "postcode": spaced,
            "risk_identified": False,
            "note": (
                "No RoFRS entry for this postcode — the Environment Agency has "
                "not flagged any properties here as at-risk of river or sea flooding. "
                "This does not cover surface-water or groundwater flood risk."
            ),
            "source": "EA RoFRS — Postcodes in Areas at Risk",
            "attribution": _ATTRIBUTION,
        }

    by_band = {
        band: {
            "residential":     row[f"res_cnt_{suffix}"] or 0,
            "non_residential": row[f"nrp_cnt_{suffix}"] or 0,
            "unclassified":    row[f"unc_cnt_{suffix}"] or 0,
            "total":           row[f"tot_cnt_{suffix}"] or 0,
        }
        for band, suffix in (
            ("high", "high"),
            ("medium", "medium"),
            ("low", "low"),
            ("very_low", "verylow"),
        )
    }
    worst = next(
        (b for b in ("high", "medium", "low", "very_low") if by_band[b]["total"] > 0),
        None,
    )

    return {
        "postcode": row["pcds"],
        "risk_identified": worst is not None,
        "worst_band": worst,
        "properties": {
            "total":           row["total_properties"] or 0,
            "residential":     row["residential"] or 0,
            "non_residential": row["non_residential"] or 0,
            "unclassified":    row["unclassified"] or 0,
        },
        "by_band": by_band,
        "source": "EA RoFRS — Postcodes in Areas at Risk",
        "attribution": _ATTRIBUTION,
    }


