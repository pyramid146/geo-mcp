"""Live tests against MDX's public ArcGIS Feature Service.

These hit the real Crown Estate endpoint at services2.arcgis.com — slow
relative to unit tests, but the API is anonymous, public, and the
response shape is the contract under test. The same pattern is used
across the suite for BGS / EA / Historic England endpoints.
"""
from __future__ import annotations

from geo_mcp.tools.marine_data_exchange import (
    _classify_collection,
    marine_survey_files_uk,
    marine_surveys_uk,
)

# pyproject.toml sets asyncio_mode=auto, so async tests are auto-marked
# without an explicit pytest.mark.asyncio. Sync tests stay sync.


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


# ---------------------------------------------------------------------------
# Drill-down: marine_survey_files_uk
# ---------------------------------------------------------------------------


# A reference series — Hornsea Project One UXO Survey (2016, Fugro).
# It's substantial (1.7 TB across 17 collections) and stable since 2021.
_HORNSEA_P1_UXO = "651"


async def test_files_returns_collections_for_known_series():
    r = await marine_survey_files_uk(series_id=_HORNSEA_P1_UXO)
    assert "error" not in r
    assert r["series_id"] == "TCE-651"
    assert r["n_collections"] >= 10
    assert len(r["collections"]) >= 10
    assert r["total_size_bytes"] > 100 * 10**9  # >100 GB total


async def test_files_accepts_int_series_id():
    # Tool should accept int as well as str (ArcGIS returns numeric).
    r = await marine_survey_files_uk(series_id=int(_HORNSEA_P1_UXO))
    assert "error" not in r
    assert r["series_id"] == "TCE-651"


async def test_files_accepts_tce_prefixed_id():
    # Caller may already have the Cog Search doc id form.
    r = await marine_survey_files_uk(series_id="TCE-651")
    assert "error" not in r
    assert r["series_id"] == "TCE-651"


async def test_files_collection_shape():
    r = await marine_survey_files_uk(series_id=_HORNSEA_P1_UXO)
    c = r["collections"][0]
    for k in ("id", "name", "description", "type", "classification",
              "keywords", "size_bytes", "start_date", "end_date",
              "download_url"):
        assert k in c, f"missing field {k} in collection row"
    assert c["classification"] in {"gis_ready", "specialist", "report", "unknown"}
    assert c["download_url"].startswith("https://www.marinedataexchange.co.uk/")


async def test_files_gis_only_filters_other_classes():
    full = await marine_survey_files_uk(series_id=_HORNSEA_P1_UXO)
    gis = await marine_survey_files_uk(series_id=_HORNSEA_P1_UXO, gis_only=True)
    assert all(c["classification"] == "gis_ready" for c in gis["collections"])
    assert len(gis["collections"]) <= len(full["collections"])


async def test_files_classification_finds_shapefiles_as_gis_ready():
    r = await marine_survey_files_uk(series_id=_HORNSEA_P1_UXO)
    # The "Seabed Classification Shapefiles" collection must classify
    # gis_ready — it's the canonical example.
    shapefile_rows = [c for c in r["collections"]
                      if "shapefile" in (c.get("name") or "").lower()]
    assert shapefile_rows, "expected a Shapefiles collection in this series"
    assert all(c["classification"] == "gis_ready" for c in shapefile_rows)


async def test_files_classification_finds_segy_as_specialist():
    r = await marine_survey_files_uk(series_id=_HORNSEA_P1_UXO)
    raw_seismic = [c for c in r["collections"]
                   if "raw seismic" in (c.get("name") or "").lower()]
    assert raw_seismic, "expected a Raw Seismic Data collection"
    assert all(c["classification"] == "specialist" for c in raw_seismic)


async def test_files_classification_unknown_series_returns_not_found():
    r = await marine_survey_files_uk(series_id="9999999")
    assert r.get("error") == "not_found"


async def test_files_invalid_series_id_returns_error():
    r = await marine_survey_files_uk(series_id="")
    assert r["error"] == "invalid_series_id"


async def test_files_metadata_url_present():
    r = await marine_survey_files_uk(series_id=_HORNSEA_P1_UXO)
    assert r["metadata_url"]
    assert "medin_metadata" in r["metadata_url"]


# ---------------------------------------------------------------------------
# Classifier unit tests — pure function, no network.
# ---------------------------------------------------------------------------


def test_classifier_kingdom_in_united_kingdom_does_not_specialist():
    """Defends against the bug where ``kingdom`` matched ``United Kingdom``
    in the description and threw GIS-ready collections to specialist."""
    c = {
        "name": "Bathymetry Data",
        "description": "Survey covering the United Kingdom continental shelf.",
        "keywords": ["Bathymetry and Elevation"],
        "type": "Dataset",
    }
    assert _classify_collection(c) == "gis_ready"


def test_classifier_kingdom_project_does_specialist():
    c = {
        "name": "Kingdom Projects",
        "description": "IHS Kingdom interpretation workspace.",
        "keywords": ["Seismic reflection"],
        "type": "Dataset",
    }
    assert _classify_collection(c) == "specialist"


def test_classifier_segy_specialist():
    c = {
        "name": "Raw Sub-Bottom Profiler Data",
        "description": "Pinger SEGY and sparker SEGY files plus trackplots.",
        "keywords": ["Sedimentary structure"],
        "type": "Dataset",
    }
    # Mentions both segy AND trackplots — GIS-trumping rule means
    # gis_ready wins (the trackplot bundle is usable).
    assert _classify_collection(c) == "gis_ready"


def test_classifier_pure_segy_specialist():
    c = {
        "name": "Raw Seismic Data",
        "description": "Multichannel SEG-Y seismic reflection traces.",
        "keywords": ["Seismic reflection"],
        "type": "Dataset",
    }
    assert _classify_collection(c) == "specialist"


def test_classifier_report_type():
    c = {
        "name": "Operations Report",
        "description": "Daily reports.",
        "keywords": [],
        "type": "Report",
    }
    assert _classify_collection(c) == "report"


def test_classifier_geotiff_in_description():
    c = {
        "name": "Bathymetry Charts",
        "description": "Gridded DTM delivered as GeoTIFF rasters.",
        "keywords": [],
        "type": "Dataset",
    }
    assert _classify_collection(c) == "gis_ready"
