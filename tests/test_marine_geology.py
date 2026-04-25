"""Live tests against the BGS GeoIndex Offshore ArcGIS REST endpoint.

Hits map.bgs.ac.uk for real — these are integration tests, slow
relative to the rest of the suite. Same pattern as test_boreholes.py
and test_marine_data_exchange.py.
"""
from __future__ import annotations

from geo_mcp.tools.marine_geology import marine_geology_uk

# pyproject.toml sets asyncio_mode=auto, so async tests are auto-marked.


# Reference point — Dogger Bank wind farm zone. Heavily sampled, with
# all four layers reliably populated.
_DOGGER_LAT = 53.8927
_DOGGER_LON = 1.8751


async def test_dogger_bank_returns_all_four_layer_types():
    r = await marine_geology_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=10_000,
    )
    assert "error" not in r
    t = r["totals"]
    # The Dogger Bank area has all four layer types populated.
    assert t["samples"] >= 5
    assert t["sediment_classifications"] >= 3
    assert t["seismic_lines"] >= 5
    assert t["hydrocarbon_wells"] >= 1


async def test_samples_have_expected_shape():
    r = await marine_geology_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=10_000,
    )
    s = r["samples"][0]
    for k in (
        "sample_name", "equipment_type", "cruise", "ship",
        "water_depth_m", "geol_summary", "image_url", "distance_m",
    ):
        assert k in s, f"missing field {k} in sample row"
    # Some samples in the Dogger area have a PDF log URL.
    has_pdf = any((row.get("image_url") or "").endswith(".pdf")
                  for row in r["samples"])
    assert has_pdf, "expected at least one BGS PDF log URL in samples"


async def test_sediment_has_folk_classification():
    r = await marine_geology_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=10_000,
    )
    sed = r["sediment_classifications"][0]
    for k in ("sample_name", "folk_class", "folk_short",
              "gravel_pct", "sand_pct", "mud_pct", "distance_m"):
        assert k in sed
    # Folk fractions should sum close to 100% (ignoring rounding).
    pcts = [sed.get(p) or 0 for p in ("gravel_pct", "sand_pct", "mud_pct")]
    assert 95.0 <= sum(pcts) <= 105.0, f"Folk fractions don't sum to 100: {pcts}"


async def test_seismic_lines_have_scan_urls_when_available():
    r = await marine_geology_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=10_000,
    )
    lines = r["seismic_lines"]
    assert lines, "expected at least one seismic line near Dogger Bank"
    # Some legacy seismic lines have scan URLs to the BGS large-image
    # viewer; not all do, but at least some should.
    scanned = [l for l in lines
               if l.get("scan_url") or l.get("scan_download_url")]
    assert scanned, "expected at least one seismic line with a scan URL"


async def test_hydrocarbon_wells_have_status_and_operator():
    r = await marine_geology_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=15_000,
    )
    wells = r["hydrocarbon_wells"]
    assert wells, "expected at least one well in quadrants 47/48"
    w = wells[0]
    for k in (
        "well_name", "licence", "quadrant_block",
        "well_class", "well_status",
        "spud_date", "completion_date",
        "water_depth_m", "total_depth_m", "distance_m",
    ):
        assert k in w
    # Quadrant/block should be in the canonical "NN/NN" form (or
    # NN/NNl for licensed sub-blocks like 48/10c).
    assert "/" in (w["quadrant_block"] or "")


async def test_distance_ordering_within_each_layer():
    r = await marine_geology_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=10_000,
    )
    for kind in ("samples", "sediment_classifications",
                 "seismic_lines", "hydrocarbon_wells"):
        rows = r[kind]
        distances = [row["distance_m"] for row in rows]
        assert distances == sorted(distances), f"{kind} not in distance order"


async def test_each_layer_capped_at_25():
    r = await marine_geology_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=50_000,
    )
    for kind in ("samples", "sediment_classifications",
                 "seismic_lines", "hydrocarbon_wells"):
        assert len(r[kind]) <= 25


async def test_onshore_point_returns_zero_in_each_layer():
    # Birmingham — well inland; BGS Offshore should return nothing.
    r = await marine_geology_uk(lat=52.4862, lon=-1.8904, radius_m=5_000)
    assert "error" not in r
    for kind in ("samples", "sediment_classifications",
                 "seismic_lines", "hydrocarbon_wells"):
        assert r["totals"][kind] == 0


async def test_invalid_lat_returns_error():
    r = await marine_geology_uk(lat=999.0, lon=0.0, radius_m=1000)
    assert "error" in r


async def test_radius_capped():
    r = await marine_geology_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=500_000,
    )
    assert "error" in r


async def test_attribution_present_and_mentions_bgs():
    r = await marine_geology_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=5000,
    )
    assert "BGS" in r["attribution"]
    assert "OGL" in r["attribution"] or "Open Government Licence" in r["attribution"]
