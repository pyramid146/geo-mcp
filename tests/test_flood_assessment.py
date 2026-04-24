from __future__ import annotations

import pytest

from geo_mcp.tools.flood_assessment import flood_assessment_uk

pytestmark = pytest.mark.asyncio


async def test_tewkesbury_gl20_5by_is_high_risk():
    r = await flood_assessment_uk(postcode="GL20 5BY")
    assert "error" not in r
    assert r["verdict"] == "high"
    assert r["site"]["postcode"] == "GL20 5BY"
    # Narrative should mention 2007 (the Tewkesbury flood year)
    assert "2007" in r["narrative"]
    # Signals all populated
    s = r["signals"]
    assert s["planning_zone"]["zone"] in (1, 2, 3)
    assert s["probability_rofrs"]["risk_identified"] is True
    assert s["historic"]["count"] > 0
    assert s["nppf_planning"]["site"]["flood_zone"] in (1, 2, 3)


async def test_central_london_is_low_risk():
    r = await flood_assessment_uk(postcode="SW1A 1AA")
    assert r["verdict"] in {"low", "moderate"}  # Thames Barrier, but we're strict


async def test_accepts_lat_lon():
    r = await flood_assessment_uk(lat=51.5014, lon=-0.1419)
    assert "error" not in r
    assert r["site"]["postcode"] == "SW1A 1AA"


async def test_rejects_both_inputs():
    r = await flood_assessment_uk(postcode="SW1A 1AA", lat=51.5, lon=-0.1)
    assert r["error"] == "invalid_input"


async def test_rejects_neither_input():
    r = await flood_assessment_uk()
    assert r["error"] == "invalid_input"


async def test_unknown_postcode():
    r = await flood_assessment_uk(postcode="ZZ99 9ZZ")
    assert r.get("error") == "postcode_not_found"


async def test_invalid_postcode_format():
    r = await flood_assessment_uk(postcode="NOT REAL")
    assert r.get("error") == "invalid_postcode"


async def test_single_pre_1990_historic_event_does_not_escalate_to_high():
    # GL20 5SN sits in Tewkesbury but outside the 2007-era flood outlines —
    # only the 1947 Lower-Severn record covers it. A single event that old
    # should not, on its own, push the verdict to "high". This was a
    # QA-agent regression.
    r = await flood_assessment_uk(postcode="GL20 5SN")
    assert "error" not in r
    assert r["verdict"] in {"low", "moderate"}, \
        f"single 1947 event must not escalate to high, got {r['verdict']}"


async def test_welsh_point_returns_coverage_gap():
    # Snowdon summit — Wales, outside EA coverage on every flood source.
    # Must not return "low" (a silent false negative).
    r = await flood_assessment_uk(lat=53.0685, lon=-4.0765)
    assert "error" not in r
    assert r["verdict"] == "coverage_gap"
    assert "England" in r["narrative"] or "Wales" in r["narrative"]


async def test_scottish_point_returns_coverage_gap():
    r = await flood_assessment_uk(lat=55.9533, lon=-3.1883)  # Edinburgh
    assert "error" not in r
    assert r["verdict"] == "coverage_gap"
