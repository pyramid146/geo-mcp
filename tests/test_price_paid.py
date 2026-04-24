from __future__ import annotations

import pytest

from geo_mcp.tools.price_paid import recent_sales_uk

pytestmark = pytest.mark.asyncio


async def test_whitehall_court_flats():
    # SW1A 2EP — Whitehall Court, Westminster. Dense flat sales, mostly
    # leasehold, typical central-London prices.
    r = await recent_sales_uk(postcode="SW1A 2EP", years=10)
    assert "error" not in r
    assert r["count"] > 0
    stats = r["stats"]
    assert stats["mean_price"] > 100_000
    assert stats["min_price"] <= stats["median_price"] <= stats["max_price"]
    # Central London flats are almost all leasehold.
    assert stats["by_tenure"]["Leasehold"] > stats["by_tenure"]["Freehold"]


async def test_unspaced_postcode_normalised():
    r = await recent_sales_uk(postcode="sw1a2ep", years=10)
    assert r["postcode"] == "SW1A 2EP"


async def test_non_residential_postcode_zero_sales():
    # SW1A 1AA is Buckingham Palace — no recorded residential sales.
    r = await recent_sales_uk(postcode="SW1A 1AA", years=10)
    assert r["count"] == 0
    assert r["stats"] is None
    assert "note" in r


async def test_invalid_format_returns_error():
    r = await recent_sales_uk(postcode="NOT REAL")
    assert r["error"] == "invalid_postcode"


async def test_invalid_years_returns_error():
    r = await recent_sales_uk(postcode="SW1A 2EP", years=100)
    assert r["error"] == "invalid_years"


async def test_sales_returned_in_descending_date_order():
    r = await recent_sales_uk(postcode="SW1A 2EP", years=10)
    if r["count"] > 1:
        dates = [s["date"] for s in r["sales"]]
        assert dates == sorted(dates, reverse=True)


async def test_sales_respect_window():
    r = await recent_sales_uk(postcode="SW1A 2EP", years=2)
    # All returned sales must be within the window.
    start = r["window"]["from"]
    assert all(s["date"] >= start for s in r["sales"])
