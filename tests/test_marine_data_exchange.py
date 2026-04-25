"""Live tests against MDX's public ArcGIS Feature Service.

These hit the real Crown Estate endpoint at services2.arcgis.com — slow
relative to unit tests, but the API is anonymous, public, and the
response shape is the contract under test. The same pattern is used
across the suite for BGS / EA / Historic England endpoints.
"""
from __future__ import annotations

import pytest

from geo_mcp.tools.marine_data_exchange import marine_surveys_uk

pytestmark = pytest.mark.asyncio


async def test_dogger_bank_has_many_site_specific_surveys():
    # Dogger Bank wind farm zone — heavily surveyed, should reliably
    # return a substantial site-specific count regardless of MDX's
    # ongoing data deposits.
    r = await marine_surveys_uk(lat=53.8927, lon=1.8751, radius_m=5000)
    assert "error" not in r
    assert r["count"] >= 5  # site-specific
    assert r["research_count"] >= 50  # nationwide programmes
    assert r["series"], "expected at least one site-specific series in payload"
    # Site-specific results should never include phase=Research.
    for s in r["series"]:
        phase = (s.get("phase") or "").strip().lower()
        assert phase != "research"


async def test_dogger_bank_series_have_expected_fields():
    r = await marine_surveys_uk(lat=53.8927, lon=1.8751, radius_m=5000)
    s = r["series"][0]
    # Schema sanity — these are the fields agents will reason over.
    for key in (
        "series_id", "name", "site", "phase",
        "themes", "methodologies",
        "start_date", "end_date",
        "n_collections", "portal_url",
    ):
        assert key in s, f"missing field {key} in series row"
    # portal_url must be a usable URL pointing at MDX.
    assert s["portal_url"].startswith("http")
    assert "marinedataexchange" in s["portal_url"]


async def test_include_research_returns_more_series():
    base = await marine_surveys_uk(lat=53.8927, lon=1.8751, radius_m=5000)
    full = await marine_surveys_uk(
        lat=53.8927, lon=1.8751, radius_m=5000, include_research=True,
    )
    # `count` is always the site-specific count regardless of flag.
    assert full["count"] == base["count"]
    # But the `series` list grows when research is included.
    assert len(full["series"]) >= len(base["series"])


async def test_phase_breakdown_excludes_research():
    r = await marine_surveys_uk(lat=53.8927, lon=1.8751, radius_m=5000)
    assert "research" not in [k.lower().strip() for k in (r["by_phase"] or {}).keys()]


async def test_by_phase_is_keyed_on_normalised_phase():
    # MDX has trailing-whitespace variants like "Research " — our
    # by_phase aggregation should not duplicate keys for those.
    r = await marine_surveys_uk(lat=53.8927, lon=1.8751, radius_m=5000)
    seen = set()
    for k in (r["by_phase"] or {}).keys():
        # No leading/trailing whitespace allowed in keys.
        assert k == k.strip()
        # No case-only collisions.
        norm = k.lower()
        assert norm not in seen, f"duplicate phase key after lowering: {k}"
        seen.add(norm)


async def test_invalid_lat_returns_error_no_raise():
    r = await marine_surveys_uk(lat=999.0, lon=0.0, radius_m=1000)
    assert "error" in r
    assert "lat" in r["error"]


async def test_radius_capped_at_max():
    # 100km is over the 50km cap.
    r = await marine_surveys_uk(lat=53.8927, lon=1.8751, radius_m=100_000)
    assert "error" in r


async def test_inland_point_is_quieter_than_offshore():
    # Inland point should have far fewer site-specific marine surveys
    # than a heavily-surveyed offshore patch. Some series have polygons
    # large enough to graze inland (research/regional aggregation), so
    # we don't assert zero — just "much less than offshore Dogger".
    inland = await marine_surveys_uk(lat=52.4862, lon=-1.8904, radius_m=5000)
    offshore = await marine_surveys_uk(lat=53.8927, lon=1.8751, radius_m=5000)
    assert "error" not in inland
    assert inland["count"] < offshore["count"]


async def test_dates_are_iso_when_present():
    # ArcGIS returns dates as epoch-millis ints; we convert to YYYY-MM-DD.
    r = await marine_surveys_uk(lat=53.8927, lon=1.8751, radius_m=5000)
    for s in r["series"]:
        for k in ("start_date", "end_date"):
            v = s.get(k)
            if v is not None:
                # ISO date shape.
                assert len(v) == 10 and v[4] == "-" and v[7] == "-"


async def test_methodologies_is_list_or_none():
    r = await marine_surveys_uk(lat=53.8927, lon=1.8751, radius_m=5000)
    for s in r["series"]:
        m = s.get("methodologies")
        assert m is None or isinstance(m, list)


async def test_attribution_present():
    r = await marine_surveys_uk(lat=53.8927, lon=1.8751, radius_m=5000)
    assert "Crown Estate" in r["attribution"]
    assert "marinedataexchange" in r["attribution"]
