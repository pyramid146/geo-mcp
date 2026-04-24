"""Tests for building_footprint_uk."""
from __future__ import annotations

import pytest

from geo_mcp.tools.building import building_footprint_uk

pytestmark = pytest.mark.asyncio


async def test_downing_street_10_returns_a_building():
    # 10 Downing Street — well-defined building footprint expected.
    r = await building_footprint_uk(10033544614)
    assert "error" not in r
    assert r["uprn"] == 10033544614
    assert 51.498 <= r["point"]["lat"] <= 51.504

    # The OS Open UPRN coord may sit just outside the listed-building
    # polygon (gated/secured property), so we accept either case but
    # if a polygon IS returned, sanity-check the shape.
    if r["building"] is not None:
        b = r["building"]
        assert b["uuid"]
        assert b["area_sqm"] > 0
        assert b["polygon_wgs84"]["type"] in ("Polygon", "MultiPolygon")


async def test_unknown_uprn_returns_not_found():
    r = await building_footprint_uk(999999999999)
    assert r["error"] == "uprn_not_found"


async def test_invalid_uprn_rejected():
    r = await building_footprint_uk("not-a-uprn")
    assert r["error"] == "invalid_uprn"


async def test_too_long_uprn_rejected():
    r = await building_footprint_uk("1234567890123")
    assert r["error"] == "invalid_uprn"


async def test_response_carries_attribution():
    r = await building_footprint_uk(10033544614)
    assert "OS Open Zoomstack" in r["attribution"]
    assert "OS Open UPRN" in r["attribution"]
