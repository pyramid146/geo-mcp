"""Tests for property_lookup_uk."""
from __future__ import annotations

import pytest

from geo_mcp.data_access.postgis import close_pool
from geo_mcp.tools.property import property_lookup_uk

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _reset_pool():
    yield
    await close_pool()


async def test_downing_street_10_resolves_to_westminster():
    # 10 Downing Street — a publicly-known landmark UPRN.
    r = await property_lookup_uk(10033544614)
    assert "error" not in r
    assert r["uprn"] == 10033544614
    # Downing Street is at about 51.5010 N, 0.1416 W.
    assert 51.498 <= r["lat"] <= 51.504
    assert -0.145 <= r["lon"] <= -0.138
    assert r["osgb"]["easting"] > 0 and r["osgb"]["northing"] > 0
    assert r["source"] == "OS Open UPRN"

    admin = r["admin"]
    assert admin is not None
    assert admin["admin"]["country"]["code"] == "E92000001"  # England
    assert admin["admin"]["local_authority"]["name"] == "City of Westminster"


async def test_accepts_uprn_as_string():
    r = await property_lookup_uk("10033544614")
    assert "error" not in r
    assert r["uprn"] == 10033544614


async def test_unknown_uprn_returns_not_found():
    # 999999999999 is within the 12-digit range but unlikely to exist.
    r = await property_lookup_uk(999999999999)
    assert r["error"] == "uprn_not_found"


async def test_non_numeric_uprn_rejected():
    r = await property_lookup_uk("not-a-uprn")
    assert r["error"] == "invalid_uprn"


async def test_too_long_uprn_rejected():
    r = await property_lookup_uk("1234567890123")  # 13 digits
    assert r["error"] == "invalid_uprn"


async def test_empty_uprn_rejected():
    r = await property_lookup_uk("")
    assert r["error"] == "invalid_uprn"
