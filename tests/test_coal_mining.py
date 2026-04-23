"""Tests for coal_mining_risk_uk.

Live tests against the Coal Authority WMS (hosted on BGS infra) — same
pattern as test_flood_surface_water. Can flake if upstream is down;
treat occasional failures as upstream flakes.
"""
from __future__ import annotations

import pytest

from geo_mcp.data_access.postgis import close_pool
from geo_mcp.tools.coal_mining import coal_mining_risk_uk

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _reset_pool():
    yield
    await close_pool()


async def test_sheffield_centre_is_in_coalfield():
    # Central Sheffield — in the Yorkshire coalfield, known high-risk.
    r = await coal_mining_risk_uk(lat=53.3811, lon=-1.4701)
    assert "error" not in r
    assert r["verdict"] in ("coalfield_high_risk", "coalfield_low_risk")
    assert r["signals"]["coal_mining_reporting_area"] is True


async def test_central_london_is_outside_coalfield():
    # Westminster — nowhere near a coalfield.
    r = await coal_mining_risk_uk(lat=51.5014, lon=-0.1419)
    assert "error" not in r
    assert r["verdict"] == "outside_coalfield"
    assert r["signals"]["coal_mining_reporting_area"] is False


async def test_northern_ireland_is_coverage_gap():
    # Belfast city centre.
    r = await coal_mining_risk_uk(lat=54.5973, lon=-5.9301)
    assert r["verdict"] == "coverage_gap"
    assert "Northern Ireland" in r["narrative"]


async def test_invalid_coord_rejected():
    r = await coal_mining_risk_uk(lat=999, lon=0)
    assert "error" in r


async def test_response_carries_attribution_and_source():
    r = await coal_mining_risk_uk(lat=51.5014, lon=-0.1419)
    assert "Coal Authority" in r.get("attribution", "")
    assert "source" in r
