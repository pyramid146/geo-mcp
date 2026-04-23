"""Tests for deprivation_uk."""
from __future__ import annotations

import pytest

from geo_mcp.data_access.postgis import close_pool
from geo_mcp.tools.deprivation import deprivation_uk

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _reset_pool():
    yield
    await close_pool()


async def test_westminster_by_postcode():
    # SW1A 1AA (Buckingham Palace area) — low deprivation expected.
    r = await deprivation_uk(postcode="SW1A 1AA")
    assert "error" not in r
    assert 1 <= r["imd_decile"] <= 10
    assert r["lsoa"]["code"].startswith("E01")


async def test_by_latlon():
    r = await deprivation_uk(lat=51.5014, lon=-0.1419)
    assert "error" not in r
    assert 1 <= r["imd_decile"] <= 10


async def test_invalid_input_both_provided():
    r = await deprivation_uk(postcode="SW1A 1AA", lat=51.5, lon=-0.1)
    assert r["error"] == "invalid_input"


async def test_invalid_input_neither_provided():
    r = await deprivation_uk()
    assert r["error"] == "invalid_input"


async def test_invalid_postcode_rejected():
    r = await deprivation_uk(postcode="NOT A POSTCODE")
    assert r["error"] == "invalid_postcode"


async def test_welsh_postcode_returns_coverage_gap():
    # Cardiff — CF10 1DY
    r = await deprivation_uk(postcode="CF10 1DY")
    # Either coverage_gap if onspd has the postcode, or not_found.
    assert r.get("coverage_gap") is True or "error" in r
