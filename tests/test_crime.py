"""Tests for crime_nearby_uk."""
from __future__ import annotations

import pytest

from geo_mcp.tools.crime import crime_nearby_uk

pytestmark = pytest.mark.asyncio


async def test_central_london_returns_crimes():
    # Westminster area: always lots of crime of many types.
    r = await crime_nearby_uk(lat=51.5014, lon=-0.1419, radius_m=500, months=12)
    assert "error" not in r
    assert r["count"] > 100  # anything less would be suspicious
    assert len(r["by_crime_type"]) >= 5  # multiple categories
    assert len(r["by_month"]) >= 6       # spanning months


async def test_by_month_keys_are_yyyy_mm():
    r = await crime_nearby_uk(lat=51.5014, lon=-0.1419, radius_m=300, months=6)
    if r.get("by_month"):
        assert all(len(m["month"]) == 7 and m["month"][4] == "-" for m in r["by_month"])


async def test_scottish_point_returns_coverage_note():
    # Edinburgh city centre.
    r = await crime_nearby_uk(lat=55.9533, lon=-3.1883, radius_m=500, months=12)
    assert "error" not in r
    assert r["count"] == 0
    assert r["coverage_note"] is not None
    assert "Scotland" in r["coverage_note"]


async def test_invalid_radius_rejected():
    r = await crime_nearby_uk(lat=51.5, lon=-0.14, radius_m=10_000)
    assert "error" in r


async def test_invalid_months_rejected():
    r = await crime_nearby_uk(lat=51.5, lon=-0.14, radius_m=500, months=100)
    assert r["error"] == "invalid_months"


async def test_out_of_uk_returns_empty_not_error():
    r = await crime_nearby_uk(lat=48.8566, lon=2.3522, radius_m=500)  # Paris
    assert "error" not in r
    assert r["count"] == 0
