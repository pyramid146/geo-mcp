from __future__ import annotations

import pytest

from geo_mcp.tools.flood_surface_water import surface_water_risk_uk

pytestmark = pytest.mark.asyncio


async def test_returns_a_band_for_any_english_point():
    # Outside a risk polygon is "Very Low" — so any valid England point
    # should at least return a band.
    r = await surface_water_risk_uk(lat=51.5014, lon=-0.1419)
    assert "error" not in r
    assert r["band"] in {"Very Low", "Low", "Medium", "High"}


async def test_wales_returns_very_low_with_coverage_note():
    r = await surface_water_risk_uk(lat=53.0685, lon=-4.0765)
    assert r["band"] == "Very Low"
    assert "England only" in r["coverage_note"]


async def test_invalid_lat_returns_error():
    r = await surface_water_risk_uk(lat=99.0, lon=0.0)
    assert r["error"] == "invalid_lat"
