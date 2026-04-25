"""Live tests against NSTA's public ArcGIS Online feature services."""
from __future__ import annotations

from geo_mcp.tools.marine_nsta import marine_nsta_uk

# pyproject.toml sets asyncio_mode=auto.

# Reference points.
_DOGGER_LAT, _DOGGER_LON = 53.8927, 1.8751   # Dogger Bank — heavy NSTA activity
_INLAND_LAT, _INLAND_LON = 52.4862, -1.8904  # Birmingham
_NORTH_SEA_OIL_LAT, _NORTH_SEA_OIL_LON = 58.0, 1.5  # North Sea oil heartland


async def test_dogger_bank_returns_expected_classes():
    r = await marine_nsta_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=50_000,
    )
    assert "error" not in r
    t = r["totals"]
    # Dogger Bank: lots of seismic + a few hydrocarbon fields nearby
    # plus the BP/Equinor Endurance CO2 storage licence area.
    assert t["seismic_3d"] >= 5
    assert t["seismic_2d"] >= 5
    assert t["hydrocarbon_fields"] >= 5
    assert t["petroleum_licences"] >= 5
    assert t["co2_storage_licences"] >= 1


async def test_birmingham_inland_returns_zero():
    r = await marine_nsta_uk(lat=_INLAND_LAT, lon=_INLAND_LON, radius_m=5_000)
    assert "error" not in r
    for kind in ("hydrocarbon_fields", "petroleum_licences",
                 "seismic_3d", "seismic_2d", "pipelines",
                 "co2_storage_licences"):
        assert r["totals"][kind] == 0


async def test_north_sea_oil_heartland_has_pipelines_and_fields():
    r = await marine_nsta_uk(
        lat=_NORTH_SEA_OIL_LAT, lon=_NORTH_SEA_OIL_LON, radius_m=50_000,
    )
    assert "error" not in r
    t = r["totals"]
    # Brent / Forties / Beryl heartland — should have pipelines + many fields.
    assert t["hydrocarbon_fields"] >= 3
    assert t["pipelines"] >= 1


async def test_field_record_has_expected_fields():
    r = await marine_nsta_uk(
        lat=_NORTH_SEA_OIL_LAT, lon=_NORTH_SEA_OIL_LON, radius_m=50_000,
    )
    assert r["hydrocarbon_fields"], "expected ≥1 hydrocarbon field"
    f = r["hydrocarbon_fields"][0]
    for k in ("field_name", "field_type", "status",
              "discovery_date", "discovery_well"):
        assert k in f


async def test_licence_record_has_expected_fields():
    r = await marine_nsta_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=50_000,
    )
    assert r["petroleum_licences"]
    l = r["petroleum_licences"][0]
    for k in ("licence_ref", "licence_type", "status"):
        assert k in l


async def test_co2_record_has_partners_list():
    r = await marine_nsta_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=50_000,
    )
    co2 = r["co2_storage_licences"]
    assert co2, "Endurance CO2 licence should be within 50 km of Dogger Bank"
    c = co2[0]
    assert "licence_ref" in c
    assert isinstance(c.get("partners"), list)


async def test_seismic_3d_record_has_survey_name():
    r = await marine_nsta_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=50_000,
    )
    s = r["seismic_3d"][0]
    assert s.get("survey_name")
    # Should be a string, not numeric noise.
    assert isinstance(s["survey_name"], str)


async def test_each_layer_capped_at_25():
    r = await marine_nsta_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=100_000,
    )
    for kind in ("hydrocarbon_fields", "petroleum_licences",
                 "seismic_3d", "seismic_2d", "pipelines",
                 "co2_storage_licences"):
        assert len(r[kind]) <= 25


async def test_invalid_lat_returns_error():
    r = await marine_nsta_uk(lat=999.0, lon=0.0, radius_m=1000)
    assert "error" in r


async def test_radius_capped():
    r = await marine_nsta_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=500_000,
    )
    assert "error" in r


async def test_attribution_credits_nsta_and_explains_gating():
    r = await marine_nsta_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=10_000,
    )
    a = r["attribution"]
    # Must credit NSTA + acknowledge that the deeper NDR is gated.
    assert "NSTA" in a
    assert "Open" in a or "OGL" in a
    assert "ndr.nstauthority.co.uk" in a or "registration" in a
