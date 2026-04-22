from __future__ import annotations

import pytest

from geo_mcp.data_access.postgis import close_pool
from geo_mcp.tools.geocoding import reverse_geocode_uk

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _reset_pool():
    # pytest-asyncio creates a fresh event loop per test by default; a pool
    # created on one loop can't be reused from another. Close after each test.
    yield
    await close_pool()


async def test_buckingham_palace_returns_sw1a_1aa_with_names():
    # Buckingham Palace is inside the SW1A 1AA postcode centroid area.
    result = await reverse_geocode_uk(lat=51.5014, lon=-0.1419)

    assert "error" not in result
    assert result["postcode"] == "SW1A 1AA"
    assert result["distance_m"] < 100

    admin = result["admin"]
    assert admin["country"] == {"code": "E92000001", "name": "England"}
    assert admin["region"] == {"code": "E12000007", "name": "London"}
    assert admin["local_authority"]["code"] == "E09000033"
    assert admin["local_authority"]["name"] == "City of Westminster"
    # LSOA / MSOA only carry codes — no name register yet.
    assert admin["lsoa"]["code"].startswith("E01")
    assert admin["lsoa"]["name"] is None

    assert "Open Government Licence" in result["attribution"]
    assert "Boundary-Line" in result["source"]
    # Enrichment added 2026-04-21: geology block should appear for any
    # GB postcode where BGS has coverage. Central London is in the
    # Thames Group.
    assert result["geology"] is not None
    assert result["geology"]["bedrock"]["formation_name"]
    assert "Geology" in result["source"]


async def test_lat_out_of_range_returns_error():
    result = await reverse_geocode_uk(lat=95.0, lon=0.0)
    assert result["error"] == "invalid_lat"


async def test_lon_out_of_range_returns_error():
    result = await reverse_geocode_uk(lat=51.5, lon=200.0)
    assert result["error"] == "invalid_lon"


async def test_mid_atlantic_returns_far_postcode_not_error():
    # The tool does not clip to UK — it returns nearest regardless. An agent
    # can decide what to do with distance_m. Verify we get a sensible result
    # rather than an exception.
    result = await reverse_geocode_uk(lat=40.0, lon=-30.0)
    assert "error" not in result
    assert result["distance_m"] > 1_000_000  # > 1000 km away
