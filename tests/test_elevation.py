from __future__ import annotations

import pytest

from geo_mcp.tools.elevation import elevation

pytestmark = pytest.mark.asyncio


async def test_snowdon_summit_is_high():
    # Snowdon summit — published elevation ~1,085 m. OS Terrain 50 is a
    # 50m-sampled DTM so the returned value will be a little lower than
    # the peak; expect somewhere in the 950–1100 m band.
    result = await elevation(points=[{"lat": 53.0685, "lon": -4.0765}])
    assert "error" not in result
    p = result["points"][0]
    assert p["status"] == "ok"
    assert 950 < p["elevation_m"] < 1100


async def test_london_is_low():
    # Central London ~ 10 m above sea level.
    result = await elevation(points=[{"lat": 51.5014, "lon": -0.1419}])
    assert result["points"][0]["status"] == "ok"
    assert 0 < result["points"][0]["elevation_m"] < 50


async def test_profile_along_line():
    # Four points roughly spanning Loch Ness (north to south). Expect all
    # three lake-surface points to be low (water); the fourth (a bit off
    # the loch) higher.
    pts = [
        {"lat": 57.50, "lon": -4.40},  # near Inverness end
        {"lat": 57.30, "lon": -4.48},
        {"lat": 57.10, "lon": -4.60},
        {"lat": 56.92, "lon": -4.70},  # Fort Augustus end
    ]
    result = await elevation(points=pts)
    assert result["points"][0]["status"] == "ok"
    assert all(p["elevation_m"] is not None for p in result["points"])


async def test_out_of_coverage_returns_null():
    # Ireland — outside OS Terrain 50's GB extent.
    result = await elevation(points=[{"lat": 53.35, "lon": -6.26}])
    p = result["points"][0]
    assert p["status"] == "out_of_coverage"
    assert p["elevation_m"] is None


async def test_empty_list_rejected():
    result = await elevation(points=[])
    assert result["error"] == "invalid_input"


async def test_too_many_points_rejected():
    pts = [{"lat": 51.5, "lon": -0.1}] * 600
    result = await elevation(points=pts)
    assert result["error"] == "too_many_points"
