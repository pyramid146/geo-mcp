from __future__ import annotations

import pytest

from geo_mcp.tools.flood_probability import flood_risk_probability_uk


@pytest.mark.asyncio
async def test_gl20_5by_is_high_risk():
    # Tewkesbury's Severn-Avon confluence — well known high flood risk.
    r = await flood_risk_probability_uk("GL20 5BY")
    assert "error" not in r
    assert r["risk_identified"] is True
    assert r["worst_band"] == "high"
    assert r["by_band"]["high"]["residential"] > 50
    assert r["properties"]["residential"] >= r["by_band"]["high"]["residential"]


@pytest.mark.asyncio
async def test_unspaced_lowercase_normalizes():
    r = await flood_risk_probability_uk("gl205by")
    assert r["postcode"] == "GL20 5BY"
    assert r["risk_identified"] is True


@pytest.mark.asyncio
async def test_postcode_outside_rofrs_returns_no_risk():
    # Any postcode in the middle of nowhere. Picking a Manchester central
    # postcode that's away from any river/sea.
    r = await flood_risk_probability_uk("M1 1AA")
    assert "error" not in r
    assert r["risk_identified"] is False
    assert "note" in r


@pytest.mark.asyncio
async def test_invalid_format_returns_error():
    r = await flood_risk_probability_uk("NOT A POSTCODE")
    assert r["error"] == "invalid_postcode"


@pytest.mark.asyncio
async def test_empty_string_returns_error():
    r = await flood_risk_probability_uk("   ")
    assert r["error"] == "invalid_postcode"
