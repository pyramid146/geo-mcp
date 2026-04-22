from __future__ import annotations

import pytest

from geo_mcp.tools.flood_re import flood_re_eligibility_uk

pytestmark = pytest.mark.asyncio


async def test_classic_eligible_home():
    r = await flood_re_eligibility_uk(
        country="England",
        property_type="residential",
        build_year=1970,
    )
    assert r["eligible"] == "likely_eligible"
    assert r["missing_inputs"] == []


async def test_new_build_excluded():
    r = await flood_re_eligibility_uk(
        country="England",
        property_type="residential",
        build_year=2015,
    )
    assert r["eligible"] == "ineligible"
    assert "2008" in " ".join(r["reasons"])


async def test_commercial_excluded():
    r = await flood_re_eligibility_uk(
        country="England",
        property_type="commercial",
        build_year=1950,
    )
    assert r["eligible"] == "ineligible"
    assert "commercial" in " ".join(r["reasons"]).lower()


async def test_insufficient_information():
    r = await flood_re_eligibility_uk(country="England")
    assert r["eligible"] == "insufficient_information"
    assert "property_type" in r["missing_inputs"]
    assert "build_year" in r["missing_inputs"]


async def test_big_block_on_commercial_policy():
    r = await flood_re_eligibility_uk(
        country="England",
        property_type="residential",
        build_year=1970,
        flats_in_block=12,
        commercial_policy=True,
    )
    assert r["eligible"] == "ineligible"


async def test_invalid_country():
    r = await flood_re_eligibility_uk(country="Germany", property_type="residential", build_year=2000)
    assert r["error"] == "invalid_country"
