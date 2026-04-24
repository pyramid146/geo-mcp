from __future__ import annotations

import pytest

from geo_mcp.data_access.postgis import close_pool
from geo_mcp.tools.flood_summary import flood_risk_summary_uk

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _reset_pool():
    yield
    await close_pool()


async def test_postcode_district_ba14():
    r = await flood_risk_summary_uk("BA14")
    assert "error" not in r
    assert r["area"]["method"] == "postcode_district"
    assert r["postcodes_considered"] > 1000
    assert sum(r["by_zone"].values()) == r["postcodes_considered"]
    assert r["worst_zone"] in {1, 2, 3}
    # BA14 (Trowbridge area) has some known flood-zone-3 postcodes.
    assert r["by_zone"]["3"] >= 1


async def test_place_name_resolves_via_opennames():
    r = await flood_risk_summary_uk("Trowbridge")
    assert "error" not in r
    assert r["area"]["method"] == "place_name"
    assert "BA14" in r["area"]["resolved_to"]


async def test_sw1a_thames_adjacent_high_flood_pct():
    # SW1A sits along the Thames — unusually high pct-in-flood-zone for a
    # central-London postcode district.
    r = await flood_risk_summary_uk("SW1A")
    assert "error" not in r
    assert r["pct_in_any_flood_zone"] > 10


async def test_response_carries_rofrs_probability_block():
    r = await flood_risk_summary_uk("BA14")
    assert "error" not in r
    assert r["probability"] is not None
    prob = r["probability"]
    assert prob["postcodes_with_rofrs_entry"] > 0
    # The high-and-above superset must include the high-only count.
    assert prob["postcodes_with_residential_medium_plus"] >= prob["postcodes_with_residential_high"]
    by_band = prob["residential_properties_by_band"]
    assert set(by_band.keys()) == {"high", "medium", "low", "very_low"}
    assert all(v >= 0 for v in by_band.values())


async def test_lad_name_returns_area_too_large():
    r = await flood_risk_summary_uk("Wiltshire")
    assert r["error"] == "area_too_large"
    assert r["postcodes_considered"] > 5000
    assert "postcode district" in r["message"]


async def test_lad_gss_code_returns_area_too_large():
    r = await flood_risk_summary_uk("E06000054")  # Wiltshire
    assert r["error"] == "area_too_large"


async def test_unresolved_area_returns_error():
    r = await flood_risk_summary_uk("Zzyxfoosplat")
    assert r["error"] == "unresolved_area"


async def test_empty_input_returns_error():
    r = await flood_risk_summary_uk("   ")
    assert r["error"] == "invalid_input"


async def test_welsh_postcode_district_is_coverage_gap():
    # CF10 is central Cardiff — no EA Flood Map coverage.
    # Should flip verdict=coverage_gap, not silently report zone 1.
    r = await flood_risk_summary_uk("CF10")
    assert r.get("verdict") == "coverage_gap"
    assert r["postcodes_in_england"] == 0
    assert "NRW" in r["message"] or "Wales" in r["message"] or "England" in r["message"]


async def test_scottish_postcode_district_is_coverage_gap():
    # EH1 is central Edinburgh — no EA Flood Map coverage.
    r = await flood_risk_summary_uk("EH1")
    assert r.get("verdict") == "coverage_gap"
    assert r["postcodes_in_england"] == 0
