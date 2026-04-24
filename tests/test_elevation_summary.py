from __future__ import annotations

import pytest

from geo_mcp.tools.elevation_summary import elevation_summary_uk

pytestmark = pytest.mark.asyncio


async def test_plymouth_is_coastal_low_elevation():
    r = await elevation_summary_uk("Plymouth")
    assert "error" not in r
    e = r["elevation_m"]
    assert e["min"] < 5     # coastal, some cells below sea level possible
    assert e["mean"] < 30
    assert r["out_of_coverage"] == 0


async def test_sheffield_is_hilly():
    r = await elevation_summary_uk("Sheffield")
    assert "error" not in r
    assert r["postcodes_considered"] > 5000  # full LAD
    # Sheffield borders the Peak District; expect significant elevation range.
    assert r["elevation_m"]["max"] > 250
    assert r["elevation_m"]["p90"] > 150


async def test_place_name_resolution_via_opennames():
    r = await elevation_summary_uk("Trowbridge")
    assert r["area"]["method"] == "place_name"
    assert "BA14" in r["area"]["resolved_to"]


async def test_lad_scale_works_unlike_flood_summary():
    # Elevation can handle LADs because COG sampling is cheap.
    r = await elevation_summary_uk("E06000054")  # Wiltshire
    assert "error" not in r
    assert r["postcodes_considered"] > 10_000
    assert r["valid_samples"] >= r["postcodes_considered"] - 50  # ~all covered


async def test_unresolved_area_returns_error():
    r = await elevation_summary_uk("Zzyxfoosplat")
    assert r["error"] == "unresolved_area"


async def test_empty_input_returns_error():
    r = await elevation_summary_uk("")
    assert r["error"] == "invalid_input"
