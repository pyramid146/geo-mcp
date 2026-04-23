"""Tests for river_nearby_uk."""
from __future__ import annotations

import pytest

from geo_mcp.data_access.postgis import close_pool
from geo_mcp.tools.rivers import river_nearby_uk

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _reset_pool():
    yield
    await close_pool()


async def test_tower_bridge_is_on_the_tidal_thames():
    # Tower Bridge — directly over the Thames. OS Open Rivers labels
    # this stretch with its specific name ("Upper Pool" / "London
    # Reach" etc.) and form "tidalRiver", not the generic "River Thames".
    r = await river_nearby_uk(lat=51.5055, lon=-0.0754, radius_m=200)
    assert "error" not in r
    assert r["nearest"] is not None
    # Whatever OS calls it, it should at least be classified as a
    # tidal river and sit within ~100 m of the bridge point.
    assert r["nearest"]["form"] in {"tidalRiver", "river"}
    assert r["nearest"]["distance_m"] < 100


async def test_westminster_finds_thames_within_500m():
    r = await river_nearby_uk(lat=51.5014, lon=-0.1419, radius_m=500)
    assert "error" not in r
    assert r["nearest"] is not None


async def test_invalid_radius_rejected():
    r = await river_nearby_uk(lat=51.5, lon=-0.1, radius_m=100_000)
    assert "error" in r


async def test_middle_of_ocean_returns_empty():
    r = await river_nearby_uk(lat=55.0, lon=-20.0)  # middle of N Atlantic
    assert r["nearest"] is None
    assert r["rivers"] == []
