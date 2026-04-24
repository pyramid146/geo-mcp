"""Tests for title_polygon_uk.

Since HMLR INSPIRE data requires a manual registration + download,
the staging table isn't guaranteed to exist in a dev environment.
These tests verify the graceful data_not_loaded behaviour and the
input-validation path; actual polygon lookups are exercised only
when the table is present.
"""
from __future__ import annotations

import pytest

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools.inspire_polygon import title_polygon_uk

pytestmark = pytest.mark.asyncio


async def _table_exists() -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        v = await conn.fetchval("SELECT to_regclass('staging.hmlr_inspire_polygons')")
    return v is not None


async def test_missing_lat_lon_rejected():
    r = await title_polygon_uk()
    assert r["error"] == "invalid_input"


async def test_behaviour_depends_on_table_presence():
    r = await title_polygon_uk(lat=51.5014, lon=-0.1419)
    if await _table_exists():
        # Either returns a polygon or null, no error.
        assert "error" not in r
        assert "title" in r
    else:
        assert r["error"] == "data_not_loaded"
