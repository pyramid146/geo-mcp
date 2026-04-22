from __future__ import annotations

import pytest

from geo_mcp.data_access.postgis import close_pool
from geo_mcp.tools.flood_planning import nppf_planning_context_uk

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _reset_pool():
    yield
    await close_pool()


async def test_zone_3_dwelling_triggers_exception_test():
    # Somerset Levels — Flood Zone 3 territory.
    r = await nppf_planning_context_uk(
        lat=51.0783, lon=-2.9167,
        proposed_vulnerability="more_vulnerable",
    )
    assert "error" not in r
    assert r["site"]["flood_zone"] == 3
    assert r["sequential_test_required"] is True
    assert r["exception_test_required"] is True
    assert r["compatibility"] == "exception_test"


async def test_zone_1_dwelling_no_tests_required():
    # SW1A 1AA — central London, Flood Zone 1
    r = await nppf_planning_context_uk(
        lat=51.5014, lon=-0.1419,
        proposed_vulnerability="more_vulnerable",
    )
    assert r["site"]["flood_zone"] == 1
    assert r["sequential_test_required"] is False
    assert r["compatibility"] == "permitted"


async def test_highly_vulnerable_in_zone_3_not_permitted():
    r = await nppf_planning_context_uk(
        lat=51.0783, lon=-2.9167,
        proposed_vulnerability="highly_vulnerable",
    )
    assert r["compatibility"] == "not_permitted"


async def test_omitted_vulnerability_returns_matrix():
    r = await nppf_planning_context_uk(lat=51.0783, lon=-2.9167)
    assert "by_vulnerability_class" in r
    assert "more_vulnerable" in r["by_vulnerability_class"]
    assert r["exception_test_required"] is None


async def test_invalid_vulnerability_returns_error():
    r = await nppf_planning_context_uk(
        lat=51.5, lon=-0.1,
        proposed_vulnerability="not_a_real_class",
    )
    assert r["error"] == "invalid_vulnerability"
