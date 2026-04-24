from __future__ import annotations

import pytest

from geo_mcp.tools.flood_historic import historic_floods_uk

pytestmark = pytest.mark.asyncio


async def test_tewkesbury_has_multiple_recorded_floods():
    # A known repeat-flood hot spot on the Severn-Avon confluence.
    r = await historic_floods_uk(lat=51.9890, lon=-2.1723)
    assert "error" not in r
    assert r["count"] >= 5
    assert "main river" in r["by_source"]
    # The 2007 Tewkesbury floods are in the record — most-recent should
    # not be earlier than the 1990s.
    assert r["most_recent"] >= "1990"


async def test_boscastle_shows_2004_flash_flood():
    # The August 2004 Boscastle flash flood — one canonical recorded event.
    r = await historic_floods_uk(lat=50.6896, lon=-4.6925)
    assert r["count"] >= 1
    # At least one event named Boscastle (or its ID-prefixed name) should
    # appear in the list.
    names = " ".join(e["name"] or "" for e in r["events"]).lower()
    assert "boscastle" in names


async def test_sw1a_central_london_zero_recorded():
    # Thames Barrier keeps central London out of the outlines.
    r = await historic_floods_uk(lat=51.5014, lon=-0.1419)
    assert r["count"] == 0
    assert r["events"] == []


async def test_wales_returns_zero_with_coverage_note():
    # Snowdon — outside England, expected no coverage.
    r = await historic_floods_uk(lat=53.0685, lon=-4.0765)
    assert r["count"] == 0
    assert "England only" in r["coverage_note"]


async def test_lat_out_of_range_returns_error():
    r = await historic_floods_uk(lat=91.0, lon=0.0)
    assert r["error"] == "invalid_lat"


async def test_undated_sentinel_filtered_from_earliest():
    # No easy way to synthesize, but we can at least assert that when
    # earliest is returned, it's post-1800.
    r = await historic_floods_uk(lat=51.9890, lon=-2.1723)
    if r["earliest"] is not None:
        assert r["earliest"] >= "1800"
