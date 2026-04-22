from __future__ import annotations

import pytest

from geo_mcp.tools.distance import distance_between

pytestmark = pytest.mark.asyncio


async def test_manchester_to_birmingham():
    # Great-circle distance is ~ 114 km.
    r = await distance_between(lat1=53.4808, lon1=-2.2426, lat2=52.4862, lon2=-1.8904)
    assert "error" not in r
    assert 110_000 < r["great_circle_m"] < 120_000
    assert 110_000 < r["projected_m"] < 120_000
    # Manchester to Birmingham is roughly south-south-east — azimuth ~ 160°.
    assert 150 < r["azimuth_deg"] < 180


async def test_identical_points_zero():
    r = await distance_between(lat1=51.5, lon1=-0.1, lat2=51.5, lon2=-0.1)
    assert r["great_circle_m"] == 0
    assert r["projected_m"] == 0


async def test_invalid_latitude_returns_error():
    r = await distance_between(lat1=91.0, lon1=0.0, lat2=0.0, lon2=0.0)
    assert r["error"] == "invalid_lat1"
