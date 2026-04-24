"""Tests for green_space_nearby_uk."""
from __future__ import annotations

import pytest

from geo_mcp.tools.greenspace import green_space_nearby_uk

pytestmark = pytest.mark.asyncio


async def test_central_london_returns_green_spaces():
    # Westminster — lots of Royal Parks nearby.
    r = await green_space_nearby_uk(lat=51.5014, lon=-0.1419, radius_m=500)
    assert "error" not in r
    assert r["total"] >= 1
    # Park-or-garden is always central London's biggest category.
    functions = {g["function"] for g in r["greenspaces"]}
    assert "Public Park Or Garden" in functions or "Other Sports Facility" in functions


async def test_function_filter_is_respected():
    r = await green_space_nearby_uk(
        lat=51.5014, lon=-0.1419, radius_m=2000,
        functions=["Public Park Or Garden"],
    )
    assert "error" not in r
    if r["total"]:
        assert all(g["function"] == "Public Park Or Garden" for g in r["greenspaces"])


async def test_invalid_function_rejected():
    r = await green_space_nearby_uk(
        lat=51.5, lon=-0.1, functions=["Skate Park"],  # not in the 10 valid
    )
    assert r["error"] == "invalid_functions"


async def test_invalid_radius_rejected():
    r = await green_space_nearby_uk(lat=51.5, lon=-0.1, radius_m=100_000)
    assert "error" in r


async def test_out_of_uk_returns_empty():
    r = await green_space_nearby_uk(lat=48.8566, lon=2.3522)  # Paris
    assert "error" not in r
    assert r["total"] == 0
