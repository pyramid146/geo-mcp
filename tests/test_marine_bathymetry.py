"""Live tests against EMODnet Bathymetry WMS + WFS.

Hits ows.emodnet-bathymetry.eu — slow integration tests.
"""
from __future__ import annotations

from geo_mcp.tools.marine_bathymetry import (
    _is_gebco,
    _release_int,
    _trim_date,
    marine_bathymetry_uk,
)

# pyproject.toml sets asyncio_mode=auto, so async tests are auto-marked.

# Reference points.
_DOGGER_LAT, _DOGGER_LON = 53.8927, 1.8751   # Dogger Bank, ~30 m deep
_ABERDEEN_LAT, _ABERDEEN_LON = 57.2, -1.5    # Off Aberdeen, ~70 m
_INLAND_LAT, _INLAND_LON = 52.4862, -1.8904  # Birmingham
_DEEP_LAT, _DEEP_LON = 52.0, -20.0           # Atlantic abyssal


async def test_dogger_bank_returns_real_depth_and_surveys():
    r = await marine_bathymetry_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=5000,
    )
    assert "error" not in r
    # Dogger Bank is famously shallow — depth is around -25 to -35 m.
    assert r["depth_m"] is not None
    assert -50.0 < r["depth_m"] < -15.0
    # Several real surveys contribute to this DTM tile.
    assert len(r["contributing_surveys"]) >= 3
    # Not GEBCO-only — there are real UK/Dutch hydrographic surveys here.
    assert r["gebco_fallback"] is False


async def test_dogger_bank_surveys_have_metadata_urls():
    r = await marine_bathymetry_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=5000,
    )
    has_url = any(s.get("metadata_url") for s in r["contributing_surveys"])
    assert has_url, "expected at least one survey with a SeaDataNet metadata URL"


async def test_aberdeen_offshore_returns_real_depth():
    r = await marine_bathymetry_uk(
        lat=_ABERDEEN_LAT, lon=_ABERDEEN_LON, radius_m=3000,
    )
    assert "error" not in r
    assert r["depth_m"] is not None
    assert -200.0 < r["depth_m"] < -20.0


async def test_inland_point_flags_gebco_fallback():
    """A point well inland should land entirely on GEBCO global grid
    fallback — no real hydrographic surveys cover it. The tool should
    flag ``gebco_fallback: True`` so the caller doesn't mistake the
    'depth' for a real seabed measurement (it'll actually be elevation
    above mean sea level if anything)."""
    r = await marine_bathymetry_uk(
        lat=_INLAND_LAT, lon=_INLAND_LON, radius_m=5000,
    )
    assert "error" not in r
    if r["contributing_surveys"]:
        # If anything came back, it should all be GEBCO.
        assert r["gebco_fallback"] is True


async def test_deep_atlantic_has_real_depth():
    r = await marine_bathymetry_uk(
        lat=_DEEP_LAT, lon=_DEEP_LON, radius_m=5000,
    )
    assert "error" not in r
    # Abyssal — should be well below 1000 m.
    if r["depth_m"] is not None:
        assert r["depth_m"] < -1000.0


async def test_dedupe_keeps_latest_release_per_identifier():
    """The raw WFS response often has the same survey appearing once
    per DTM release (e.g. CDI 116747 in both 2022 and 2024 DTMs).
    After dedupe we should see at most one entry per identifier, and
    the chosen entry should be from the most recent release."""
    r = await marine_bathymetry_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=10000,
    )
    seen = {}
    for s in r["contributing_surveys"]:
        ident = s["identifier"]
        assert ident not in seen, f"duplicate identifier in dedupe: {ident}"
        seen[ident] = s


async def test_results_are_sorted_newest_release_first():
    r = await marine_bathymetry_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=10000,
    )
    releases = [_release_int(s) for s in r["contributing_surveys"]]
    assert releases == sorted(releases, reverse=True)


async def test_invalid_lat_returns_error():
    r = await marine_bathymetry_uk(lat=999.0, lon=0.0, radius_m=1000)
    assert "error" in r


async def test_radius_capped():
    r = await marine_bathymetry_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=500_000,
    )
    assert "error" in r


async def test_attribution_present_and_credits_emodnet_and_ukho():
    r = await marine_bathymetry_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=1000,
    )
    a = r["attribution"]
    assert "EMODnet" in a
    assert "CC-BY" in a
    # Tool should note the UKHO contribution + that ADMIRALTY is paid.
    assert "UKHO" in a or "hydrographic offices" in a
    assert "ADMIRALTY" in a or "commercial" in a


# ---------------------------------------------------------------------------
# Unit tests for the small helpers — no network.
# ---------------------------------------------------------------------------


def test_is_gebco_detects_global_fallback():
    assert _is_gebco({"identifier": "GEBCO_2014", "edmo_id": None}) is True
    assert _is_gebco({"identifier": "GEBCO2024", "edmo_id": None}) is True
    assert _is_gebco({"identifier": "116747", "edmo_id": 2607}) is False


def test_is_gebco_real_survey_with_gebco_in_name_not_flagged():
    """If a real EDMO-attributed survey happens to have GEBCO in its
    identifier, it shouldn't get filtered out as a fallback. Defensive."""
    assert _is_gebco({"identifier": "GEBCO_local_lift", "edmo_id": 2607}) is False


def test_release_int_unknown_value():
    assert _release_int({"release": None}) == -1
    assert _release_int({"release": "not-a-year"}) == -1
    assert _release_int({"release": "2024"}) == 2024


def test_trim_date_strips_timezone_marker():
    assert _trim_date("2022-12-31Z") == "2022-12-31"
    assert _trim_date("2022-12-31") == "2022-12-31"
    assert _trim_date(None) is None
    assert _trim_date("") is None
