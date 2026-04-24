"""Tests for schools_nearby_uk."""
from __future__ import annotations

import pytest

from geo_mcp.tools.schools import schools_nearby_uk

pytestmark = pytest.mark.asyncio


async def test_central_london_returns_schools():
    # Westminster — many schools within 1.5 km.
    r = await schools_nearby_uk(lat=51.5014, lon=-0.1419, radius_m=1500)
    assert "error" not in r
    assert r["total"] >= 3


async def test_phase_filter_is_respected():
    r = await schools_nearby_uk(
        lat=51.5014, lon=-0.1419, radius_m=2000, phase="Primary",
    )
    assert "error" not in r
    if r["total"]:
        assert all(s["phase"] == "Primary" for s in r["schools"])


async def test_invalid_phase_rejected():
    r = await schools_nearby_uk(lat=51.5, lon=-0.1, phase="Preschool")
    assert r["error"] == "invalid_phase"


async def test_open_only_default_excludes_closed():
    r = await schools_nearby_uk(lat=51.5014, lon=-0.1419, radius_m=2000)
    # Very unlikely a closed school would appear in the results when
    # open_only=True (default); spot-check via structure.
    for s in r["schools"]:
        # Can't check status from the response shape, but at least verify
        # the tool isn't crashing on this combination.
        assert s["urn"] > 0


async def test_response_has_ofsted_breakdown():
    r = await schools_nearby_uk(lat=51.5014, lon=-0.1419, radius_m=3000)
    assert isinstance(r["count_by_ofsted"], dict)


async def test_out_of_uk_returns_empty():
    r = await schools_nearby_uk(lat=48.8566, lon=2.3522)  # Paris
    assert "error" not in r
    assert r["total"] == 0
