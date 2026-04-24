from __future__ import annotations

import pytest

from geo_mcp.tools.forward_geocoding import geocode_uk

pytestmark = pytest.mark.asyncio


async def test_postcode_spaced():
    r = await geocode_uk("SW1A 1AA")
    assert r["match_type"] == "postcode"
    assert r["confidence"] == "exact"
    assert r["context"]["postcode"] == "SW1A 1AA"
    assert r["context"]["country_code"] == "E92000001"
    assert abs(r["lat"] - 51.501) < 0.01
    assert abs(r["lon"] - -0.142) < 0.01


async def test_postcode_unspaced_and_lowercased():
    r = await geocode_uk("sw1a1aa")
    assert r["match_type"] == "postcode"
    assert r["context"]["postcode"] == "SW1A 1AA"


async def test_manchester_resolves_to_the_city():
    r = await geocode_uk("Manchester")
    assert r["match_type"] == "populated_place"
    assert r["context"]["local_type"] == "City"
    assert r["context"]["country"] == "England"
    # Manchester city centre ~ 53.48°N, -2.24°W
    assert 53.4 < r["lat"] < 53.6
    assert -2.35 < r["lon"] < -2.15


async def test_multi_match_newport_returns_alternatives():
    # There are multiple "Newport" places in the UK. Best match should
    # carry a confidence='multiple' and an alternatives list.
    r = await geocode_uk("Newport")
    assert r["match_type"] in {"populated_place", "feature"}
    if r["confidence"] == "multiple":
        assert "alternatives" in r
        assert len(r["alternatives"]) >= 1


async def test_unknown_returns_none():
    r = await geocode_uk("Zzyxfoosplat")
    assert r["match_type"] == "none"
    assert "message" in r


async def test_empty_input_is_error():
    r = await geocode_uk("   ")
    assert r["error"] == "invalid_input"
