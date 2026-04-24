"""Tests for designated_sites_nearby_uk."""
from __future__ import annotations

import pytest

from geo_mcp.tools.designated_sites import designated_sites_nearby_uk

pytestmark = pytest.mark.asyncio


async def test_cotswolds_returns_aonb_hit():
    # Chipping Campden — deep in the Cotswolds National Landscape (AONB).
    r = await designated_sites_nearby_uk(
        lat=52.0506, lon=-1.7717, radius_m=500, types=["AONB"],
    )
    assert "error" not in r
    assert r["total"] >= 1
    assert r["in_any_designation"] is True
    assert any(d["designation_type"] == "AONB" for d in r["designations"])


async def test_central_london_returns_few_or_no_hits():
    # Westminster isn't in an SSSI/AONB etc — expect zero or few hits.
    r = await designated_sites_nearby_uk(
        lat=51.5014, lon=-0.1419, radius_m=500,
    )
    assert "error" not in r
    assert r["total"] >= 0
    # At 500 m central London shouldn't be inside any designation.
    assert r["in_any_designation"] is False


async def test_type_filter_is_respected():
    # Large radius to be sure of hits — but restrict to SSSI only.
    r = await designated_sites_nearby_uk(
        lat=52.0506, lon=-1.7717, radius_m=5000, types=["SSSI"],
    )
    assert "error" not in r
    if r["total"]:
        assert all(d["designation_type"] == "SSSI" for d in r["designations"])


async def test_invalid_types_rejected():
    r = await designated_sites_nearby_uk(
        lat=51.5, lon=-0.1, types=["NotARealType"],
    )
    assert r["error"] == "invalid_types"


async def test_invalid_radius_rejected():
    r = await designated_sites_nearby_uk(lat=51.5, lon=-0.1, radius_m=100_000)
    assert "error" in r


async def test_out_of_uk_returns_empty_not_error():
    r = await designated_sites_nearby_uk(lat=48.8566, lon=2.3522)  # Paris
    assert "error" not in r
    assert r["total"] == 0
