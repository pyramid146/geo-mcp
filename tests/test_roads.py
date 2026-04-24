"""Tests for road_nearby_uk."""
from __future__ import annotations

import pytest

from geo_mcp.tools.roads import road_nearby_uk

pytestmark = pytest.mark.asyncio


async def test_westminster_finds_major_road():
    # Westminster — plenty of A-roads within 500 m.
    r = await road_nearby_uk(lat=51.5014, lon=-0.1419, radius_m=500)
    assert "error" not in r
    assert r["nearest_major"] is not None
    assert r["nearest_major"]["class"] in {"Motorway", "A Road", "B Road"}


async def test_class_filter_is_respected():
    r = await road_nearby_uk(
        lat=51.5014, lon=-0.1419, radius_m=5000, classes=["Motorway"],
    )
    assert "error" not in r
    if r["roads"]:
        assert all(x["class"] == "Motorway" for x in r["roads"])


async def test_invalid_class_rejected():
    r = await road_nearby_uk(lat=51.5, lon=-0.1, classes=["Superhighway"])
    assert r["error"] == "invalid_classes"


async def test_invalid_radius_rejected():
    r = await road_nearby_uk(lat=51.5, lon=-0.1, radius_m=100_000)
    assert "error" in r


async def test_middle_of_sea_returns_empty():
    r = await road_nearby_uk(lat=55.0, lon=-20.0)
    assert r["nearest_major"] is None
    assert r["roads"] == []
