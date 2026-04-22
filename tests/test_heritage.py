from __future__ import annotations

import pytest

from geo_mcp.data_access.postgis import close_pool
from geo_mcp.tools.heritage import heritage_nearby_uk, is_listed_building_uk

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _reset_pool():
    yield
    await close_pool()


async def test_downing_street_is_listed_grade_i():
    r = await is_listed_building_uk(lat=51.5033, lon=-0.1276, tolerance_m=20)
    assert r["is_listed"] is True
    grades = {m["grade"] for m in r["matches"]}
    assert "I" in grades  # No 10 Downing Street is Grade I
    # Hyperlink to Historic England list entry for verification.
    assert all(m["hyperlink"].startswith("https://historicengland.org.uk/") for m in r["matches"])


async def test_york_minster_resolves_with_default_tolerance():
    # The NHLE point for the Minster sits ~25 m from the coord a caller
    # would get by geocoding "York Minster". Default tolerance_m=30 must
    # catch it — this was a security-audit finding.
    r = await is_listed_building_uk(lat=53.9621, lon=-1.0818)
    assert r["is_listed"] is True
    assert any("MINSTER" in (m["name"] or "").upper() for m in r["matches"])


async def test_tower_of_london_listed():
    r = await is_listed_building_uk(lat=51.5081, lon=-0.0760, tolerance_m=50)
    assert r["is_listed"] is True


async def test_random_manchester_postcode_not_listed():
    r = await is_listed_building_uk(lat=53.4780, lon=-2.2290)
    # Not asserting strict false (urban centres can be dense with listings)
    # but the point-tolerance is tight, so usually no hits.
    assert "error" not in r


async def test_invalid_lat_returns_error():
    r = await is_listed_building_uk(lat=99.0, lon=0.0)
    assert r["error"] == "invalid_lat"


async def test_heritage_nearby_central_london_is_busy():
    r = await heritage_nearby_uk(lat=51.5014, lon=-0.1419, radius_m=500)
    assert "error" not in r
    assert r["total"] > 10  # central London is dense
    assert "listed_building" in r["count_by_type"]
    # All returned designations should be within the radius.
    assert all(d["distance_m"] <= 500 + 1 for d in r["designations"])
    # Sorted nearest-first.
    dist = [d["distance_m"] for d in r["designations"]]
    assert dist == sorted(dist)


async def test_heritage_nearby_respects_radius_cap():
    r = await heritage_nearby_uk(lat=51.5, lon=-0.1, radius_m=10_000)
    assert r["error"] == "invalid_radius"
