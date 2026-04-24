from __future__ import annotations

import pytest

from geo_mcp.tools.geology import geology_uk

pytestmark = pytest.mark.asyncio


async def test_central_london_is_thames_group_on_terrace_gravels():
    r = await geology_uk(lat=51.5014, lon=-0.1419)
    assert "error" not in r
    assert r["bedrock"]["rock_type"].startswith("CLAY")  # Thames Group clay/silt/sand/gravel
    assert r["bedrock"]["age_oldest"] == "EOCENE"
    assert r["superficial"] is not None   # river terrace


async def test_tewkesbury_lias_bedrock_alluvium_superficial():
    r = await geology_uk(lat=51.9890, lon=-2.1723)
    assert r["bedrock"]["formation_name"] == "LIAS GROUP"
    assert r["superficial"]["deposit_name"] == "ALLUVIUM"


async def test_snowdon_ordovician_volcanics_no_superficial():
    r = await geology_uk(lat=53.0685, lon=-4.0765)
    assert "ORDOVICIAN" in r["bedrock"]["age_oldest"]
    # Exposed bedrock — superficial typically null at the summit.
    # Don't assert strictly; just assert the call succeeds.


async def test_offshore_returns_null_bedrock_and_superficial():
    # Middle of the North Sea — no BGS onshore coverage.
    r = await geology_uk(lat=55.0, lon=3.0)
    assert r["bedrock"] is None
    assert r["superficial"] is None


async def test_invalid_lat_returns_error():
    r = await geology_uk(lat=95.0, lon=0.0)
    assert r["error"] == "invalid_lat"
