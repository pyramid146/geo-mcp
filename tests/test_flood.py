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
    assert result["verdict"] == "ok"
    assert result["zone"] == 1
    assert result["source"] is None


async def test_snowdon_summit_is_coverage_gap_not_fake_zone_1():
    # Snowdon is in Wales — outside the EA Flood Map coverage.
    # The tool should flag this as coverage_gap rather than silently
    # returning zone 1.
    result = await flood_risk_uk(lat=53.0685, lon=-4.0765)
    assert "error" not in result
    assert result["verdict"] == "coverage_gap"
    assert result["zone"] is None
    assert "outside England" in result["coverage_note"]


async def test_edinburgh_is_coverage_gap():
    # Scottish point — should also register as coverage_gap.
    result = await flood_risk_uk(lat=55.9533, lon=-3.1883)
    assert result["verdict"] == "coverage_gap"
    assert result["zone"] is None


async def test_lat_out_of_range_returns_error():
    result = await flood_risk_uk(lat=100.0, lon=0.0)
    assert result["error"] == "invalid_lat"
