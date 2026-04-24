"""Tests for gp_practices_nearby_uk."""
from __future__ import annotations

import pytest

from geo_mcp.tools.healthcare import gp_practices_nearby_uk

pytestmark = pytest.mark.asyncio


async def test_westminster_finds_gp_practices():
    r = await gp_practices_nearby_uk(lat=51.5014, lon=-0.1419, radius_m=2000)
    assert "error" not in r
    assert r["total"] >= 3
    # Every returned practice should have a name + postcode.
    for p in r["practices"]:
        assert p["org_code"] and p["name"] and p["postcode"]


async def test_active_only_excludes_inactive():
    r = await gp_practices_nearby_uk(lat=51.5014, lon=-0.1419, radius_m=2000, active_only=True)
    for p in r["practices"]:
        assert p["status"] == "ACTIVE"


async def test_invalid_radius_rejected():
    r = await gp_practices_nearby_uk(lat=51.5, lon=-0.1, radius_m=100_000)
    assert "error" in r


async def test_middle_of_sea_returns_empty():
    r = await gp_practices_nearby_uk(lat=55.0, lon=-20.0)
    assert r["total"] == 0
