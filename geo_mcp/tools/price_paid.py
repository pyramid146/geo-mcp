from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._validators import canonical_spaced_postcode, is_valid_uk_postcode

_ATTRIBUTION = (
    "Contains HM Land Registry Price Paid Data © Crown copyright and database "
    "right. Licensed under the Open Government Licence v3.0. This is the "
    "complete record of residential property sales in England & Wales since 1995. "
    "It does not include commercial transactions, new-build estate bulk sales "
    "(where only one master transaction is recorded), sales under the value "
    "threshold, transfers other than on sale, or any Scottish/NI transactions."
)

_PROPERTY_TYPE_LABELS = {
    "D": "Detached",
    "S": "Semi-detached",
    "T": "Terraced",
    "F": "Flat / Maisonette",
    "O": "Other",
}

_DURATION_LABELS = {
    "F": "Freehold",
    "L": "Leasehold",
    "U": "Unknown",
}


async def recent_sales_uk(
    postcode: str,
    years: int = 5,
) -> dict[str, Any]:
    """Return recent residential property sales in a UK postcode from HMLR Price Paid Data.

    HMLR's Price Paid Data is the complete record of residential property
    sales in England & Wales since 1995, published under the Open
    Government Licence. Every sale includes the price, date, postcode,
    property type (Detached / Semi / Terraced / Flat / Other), and
    tenure (Freehold / Leasehold / Unknown).

    Use this when a caller asks questions like "what has sold recently in
    this postcode?", "how much do similar properties go for?", "is the
    asking price reasonable?". For larger-area stats ("average price in
    Trowbridge"), consider ``recent_sales_summary_uk`` — this tool is
    deliberately postcode-grain.

    Filters / caveats applied automatically:
      * Excludes `ppd_category_type = 'B'` (repossessions, power-of-sale,
        court-ordered transfers) — those skew the headline stats.
      * Excludes `record_status = 'D'` (later deleted from the register).
      * No Scottish / Northern Irish data exists in this source.

    Arguments:
        postcode: UK postcode (spaced or unspaced, case-insensitive).
        years: history window in years (default 5, max 30).

    Returns:
        {
          "postcode": "SW1A 1AA",
          "window": {"from": "...", "to": "...", "years": 5},
          "count": int,
          "stats": {
              "mean_price": int, "median_price": int,
              "min_price": int, "max_price": int,
              "by_property_type": {"Detached": 3, "Flat": 8, ...},
              "by_tenure": {"Freehold": 4, "Leasehold": 12, "Unknown": 0},
              "new_build_count": int
          } | null,  # null when count == 0
          "sales": [
              {"price", "date", "property_type", "property_type_code",
               "new_build", "tenure", "paon", "saon", "street",
               "locality", "town_city", "district", "county"},
              ...  # up to 50 most-recent
          ],
          "source": "HMLR Price Paid Data",
          "attribution": "..."
        }

    On invalid postcode or bad `years`, returns
    ``{"error": ..., "message": ...}``.
    """
    if not isinstance(postcode, str) or not postcode.strip():
        return {"error": "invalid_postcode", "message": "postcode must be a non-empty string."}
    if not is_valid_uk_postcode(postcode):
        return {
            "error": "invalid_postcode",
            "message": f"{postcode!r} does not look like a UK postcode.",
        }
    if not 1 <= years <= 30:
        return {"error": "invalid_years", "message": "years must be in 1..30."}

    spaced = canonical_spaced_postcode(postcode)
    end = date.today()
    start = end - timedelta(days=365 * years + (years // 4))  # rough leap-year allowance

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT price, date_of_transfer::date AS d, property_type, old_new, duration,
                   paon, saon, street, locality, town_city, district, county
              FROM staging.price_paid
             WHERE postcode = $1
               AND date_of_transfer >= $2
               AND ppd_category_type = 'A'
               AND record_status <> 'D'
             ORDER BY date_of_transfer DESC
             LIMIT 2000
            """,
            spaced, start,
        )

    if not rows:
        return {
            "postcode": spaced,
            "window": {"from": start.isoformat(), "to": end.isoformat(), "years": years},
            "count": 0,
            "stats": None,
            "sales": [],
            "note": (
                "No sales in this postcode in the selected window. Either "
                "no transactions have occurred, or the postcode is "
                "non-residential / outside England & Wales."
            ),
            "source": "HMLR Price Paid Data",
            "attribution": _ATTRIBUTION,
        }

    prices = sorted(r["price"] for r in rows)
    n = len(prices)
    mean_price = sum(prices) // n
    median_price = (
        prices[n // 2] if n % 2 == 1
        else (prices[n // 2 - 1] + prices[n // 2]) // 2
    )

    by_type: dict[str, int] = {}
    by_tenure: dict[str, int] = {"Freehold": 0, "Leasehold": 0, "Unknown": 0}
    new_build = 0
    for r in rows:
        t_label = _PROPERTY_TYPE_LABELS.get(r["property_type"], "Other")
        by_type[t_label] = by_type.get(t_label, 0) + 1
        by_tenure[_DURATION_LABELS.get(r["duration"], "Unknown")] += 1
        if r["old_new"] == "Y":
            new_build += 1

    return {
        "postcode": spaced,
        "window": {"from": start.isoformat(), "to": end.isoformat(), "years": years},
        "count": n,
        "stats": {
            "mean_price": mean_price,
            "median_price": median_price,
            "min_price": prices[0],
            "max_price": prices[-1],
            "by_property_type": by_type,
            "by_tenure": by_tenure,
            "new_build_count": new_build,
        },
        "sales": [
            {
                "price": r["price"],
                "date": r["d"].isoformat(),
                "property_type": _PROPERTY_TYPE_LABELS.get(r["property_type"], "Other"),
                "property_type_code": r["property_type"],
                "new_build": r["old_new"] == "Y",
                "tenure": _DURATION_LABELS.get(r["duration"], "Unknown"),
                "paon": r["paon"],
                "saon": r["saon"],
                "street": r["street"],
                "locality": r["locality"],
                "town_city": r["town_city"],
                "district": r["district"],
                "county": r["county"],
            }
            for r in rows[:50]
        ],
        "source": "HMLR Price Paid Data",
        "attribution": _ATTRIBUTION,
    }
