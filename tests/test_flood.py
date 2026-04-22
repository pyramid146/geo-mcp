from __future__ import annotations

import pytest

from geo_mcp.data_access.postgis import close_pool
from geo_mcp.tools.flood import flood_risk_uk

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _reset_pool():
    yield
    await close_pool()


async def test_somerset_levels_is_zone_3():
    # Weston Zoyland, Somerset Levels — sits in the middle of extensive
    # FZ3 polygons from historic and tidal river floods.
    result = await flood_risk_uk(lat=51.0783, lon=-2.9167)
    assert "error" not in result
    assert result["zone"] == 3
    assert result["source"] in {
        "river", "sea", "river and sea", "river / undefined", "undefined", "unknown",
    }


async def test_central_london_is_zone_1():
    # SW1A 1AA area — away from the Thames floodplain.
    result = await flood_risk_uk(lat=51.5014, lon=-0.1419)
    assert "error" not in result
    assert result["zone"] == 1
    assert result["source"] is None


async def test_snowdon_summit_is_zone_1_even_though_in_wales():
    # Snowdon is in Wales so outside the dataset's coverage. The tool
    # should still return zone 1 (the default for "no polygon covers"),
    # accompanied by the coverage_note warning the caller.
    result = await flood_risk_uk(lat=53.0685, lon=-4.0765)
    assert "error" not in result
    assert result["zone"] == 1
    assert "England only" in result["coverage_note"]


async def test_lat_out_of_range_returns_error():
    result = await flood_risk_uk(lat=100.0, lon=0.0)
    assert result["error"] == "invalid_lat"
