"""Tests for property_lookup_uk."""
from __future__ import annotations

import pytest

from geo_mcp.tools.property import property_lookup_uk, property_report_uk

pytestmark = pytest.mark.asyncio


async def test_downing_street_10_resolves_to_westminster():
    # 10 Downing Street — a publicly-known landmark UPRN.
    r = await property_lookup_uk(10033544614)
    assert "error" not in r
    assert r["uprn"] == 10033544614
    # Downing Street is at about 51.5010 N, 0.1416 W.
    assert 51.498 <= r["lat"] <= 51.504
    assert -0.145 <= r["lon"] <= -0.138
    assert r["osgb"]["easting"] > 0 and r["osgb"]["northing"] > 0
    assert r["source"] == "OS Open UPRN"

    admin = r["admin"]
    assert admin is not None
    assert admin["admin"]["country"]["code"] == "E92000001"  # England
    assert admin["admin"]["local_authority"]["name"] == "City of Westminster"


async def test_accepts_uprn_as_string():
    r = await property_lookup_uk("10033544614")
    assert "error" not in r
    assert r["uprn"] == 10033544614


async def test_unknown_uprn_returns_not_found():
    # 999999999999 is within the 12-digit range but unlikely to exist.
    r = await property_lookup_uk(999999999999)
    assert r["error"] == "uprn_not_found"


async def test_non_numeric_uprn_rejected():
    r = await property_lookup_uk("not-a-uprn")
    assert r["error"] == "invalid_uprn"


async def test_too_long_uprn_rejected():
    r = await property_lookup_uk("1234567890123")  # 13 digits
    assert r["error"] == "invalid_uprn"


async def test_empty_uprn_rejected():
    r = await property_lookup_uk("")
    assert r["error"] == "invalid_uprn"


# ---------------------------------------------------------------------------
# property_report_uk — composite
# ---------------------------------------------------------------------------


async def test_report_downing_street_returns_all_blocks():
    # 10 Downing Street — listed building (Grade I), central London.
    r = await property_report_uk(10033544614)
    assert "error" not in r

    # Shape: every expected block present (even if the inner value is null
    # for "no EPC lodged" / "no sales" style cases).
    assert set(r.keys()) >= {
        "uprn", "headline", "narrative", "site",
        "epc", "sales", "listed", "heritage", "flood", "elevation",
        "attribution",
    }
    assert r["uprn"] == 10033544614

    # Site block is intact.
    assert r["site"]["lat"] > 51 and r["site"]["lat"] < 52
    assert r["site"]["admin"]["admin"]["country"]["code"] == "E92000001"

    # Heritage block should flag *at least* one asset within 500m in the
    # Westminster neighbourhood.
    assert isinstance(r["heritage"], dict)
    assert "error" not in r["heritage"]
    assert r["heritage"]["total"] > 0

    # Narrative + headline are plain-English.
    assert isinstance(r["headline"], str) and r["headline"]
    assert "UPRN 10033544614" in r["narrative"] or "Westminster" in r["narrative"]


async def test_report_unknown_uprn_preserves_error_shape():
    r = await property_report_uk(999999999999)
    assert r["error"] == "uprn_not_found"


async def test_report_invalid_uprn_rejected():
    r = await property_report_uk("not-a-uprn")
    assert r["error"] == "invalid_uprn"


async def test_report_subtool_failure_is_isolated(monkeypatch):
    # If one sub-tool raises, the rest of the report still comes back.
    from geo_mcp.tools import property as prop_mod

    async def _boom(**_kwargs):
        raise RuntimeError("simulated EA WMS outage")

    monkeypatch.setattr(prop_mod, "flood_assessment_uk", _boom)
    r = await property_report_uk(10033544614)
    assert "error" not in r
    assert r["flood"]["error"] == "subtool_failed"
    # Other blocks unaffected.
    assert "error" not in r["heritage"]
