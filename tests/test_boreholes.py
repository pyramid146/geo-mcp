from __future__ import annotations

import pytest

from geo_mcp.tools.boreholes import boreholes_nearby_uk

pytestmark = pytest.mark.asyncio


async def test_central_london_has_many_nearby_boreholes():
    # SW1A 1AA — dense urban London, many BGS records in the immediate area.
    r = await boreholes_nearby_uk(lat=51.5014, lon=-0.1419, radius_m=500)
    assert "error" not in r
    assert r["count"] > 10
    assert r["nearest_m"] is not None
    assert len(r["boreholes"]) <= 25
    # All returned boreholes should be within the radius.
    assert all(b["distance_m"] <= 500 + 1 for b in r["boreholes"])
    # They should be in ascending distance order.
    distances = [b["distance_m"] for b in r["boreholes"]]
    assert distances == sorted(distances)


async def test_north_sea_returns_zero_count():
    r = await boreholes_nearby_uk(lat=55.0, lon=3.0, radius_m=500)
    assert r["count"] == 0
    assert r["nearest_m"] is None
    assert r["boreholes"] == []


async def test_invalid_radius_returns_error():
    r = await boreholes_nearby_uk(lat=51.5, lon=-0.1, radius_m=10_000)
    assert r["error"] == "invalid_radius"


async def test_invalid_lat_returns_error():
    r = await boreholes_nearby_uk(lat=-200.0, lon=0.0)
    assert r["error"] == "invalid_lat"


async def test_zero_radius_returns_error():
    r = await boreholes_nearby_uk(lat=51.5, lon=-0.1, radius_m=0)
    assert r["error"] == "invalid_radius"
