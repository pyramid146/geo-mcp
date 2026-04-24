from __future__ import annotations

import pytest

from geo_mcp.tools.epc import _flood_re_year_signal, energy_performance_uk


# Pure-function tests don't touch the DB — no fixture marker needed.


def test_flood_re_signal_pre_2009_bands():
    for band in (
        "England and Wales: before 1900",
        "England and Wales: 1900-1929",
        "England and Wales: 1950-1966",
        "England and Wales: 1996-2002",
        "England and Wales: 2003-2006",
    ):
        assert _flood_re_year_signal(band) == "pre_2009"


def test_flood_re_signal_post_2008():
    assert _flood_re_year_signal("England and Wales: 2012 onwards") == "post_2008"


def test_flood_re_signal_spans_cutoff():
    assert _flood_re_year_signal("England and Wales: 2007 onwards") == "spans_cutoff"
    assert _flood_re_year_signal("England and Wales: 2007-2011") == "spans_cutoff"


def test_flood_re_signal_unknown():
    assert _flood_re_year_signal(None) is None
    assert _flood_re_year_signal("") is None
    assert _flood_re_year_signal("NO DATA!") is None
    assert _flood_re_year_signal("INVALID!") is None


@pytest.mark.asyncio
async def test_postcode_with_certificates_returns_summary():
    # SW1A 2EP (Whitehall Court) has substantial EPC coverage — a block
    # of long-established flats, almost all lodged.
    r = await energy_performance_uk(postcode="SW1A 2EP")
    assert "error" not in r
    assert r["postcode"] == "SW1A 2EP"
    assert r["count"] > 0
    assert r["distinct_properties"] > 0
    assert set(r["rating_distribution"].keys()) == {"A", "B", "C", "D", "E", "F", "G"}
    # Pre-1900 construction on Whitehall Court is expected.
    assert any("before 1900" in k for k in r["by_age_band"])
    # The flood_re_year_signal must be populated for the Flood Re chain.
    assert any(p["flood_re_year_signal"] == "pre_2009" for p in r["properties"])


@pytest.mark.asyncio
async def test_postcode_no_certificates_returns_empty_summary():
    # Rare postcode with no EPCs. Tool must succeed with zero-state.
    r = await energy_performance_uk(postcode="GL20 5BY")
    assert "error" not in r
    assert r["count"] == 0
    assert r["distinct_properties"] == 0


@pytest.mark.asyncio
async def test_invalid_postcode_returns_error():
    r = await energy_performance_uk(postcode="NOT POSTCODE")
    assert r["error"] == "invalid_postcode"


@pytest.mark.asyncio
async def test_invalid_uprn_returns_error():
    r = await energy_performance_uk(uprn="notanumber")
    assert r["error"] == "invalid_uprn"


@pytest.mark.asyncio
async def test_empty_input_returns_error():
    r = await energy_performance_uk()
    assert r["error"] == "invalid_input"


@pytest.mark.asyncio
async def test_uprn_unknown_returns_none_property():
    r = await energy_performance_uk(uprn="99999999999999")
    # No error — just reports that nothing was found.
    assert "error" not in r
    assert r["property"] is None
