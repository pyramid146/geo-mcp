"""Live tests against the ADMIRALTY SeaBed Mapping Service catalogue.

Hits seabedmappingservice-live.azurewebsites.net once per test run
(~47 MB JSON), then everything is served from process-local + on-disk
cache. The cache file is shared with the production tool — that's
fine, the catalogue is public read-only metadata.
"""
from __future__ import annotations

from geo_mcp.tools.marine_admiralty import (
    _bbox_overlap,
    _coords_bbox,
    _format_resolution,
    marine_admiralty_uk,
)

# pyproject.toml sets asyncio_mode=auto.

_DOGGER_LAT, _DOGGER_LON = 53.8927, 1.8751


async def test_dogger_bank_at_50km_returns_real_surveys():
    r = await marine_admiralty_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=50_000,
    )
    assert "error" not in r
    # Dogger Bank zone is heavily surveyed — expect ≥ 10.
    assert r["count"] >= 10


async def test_returned_surveys_have_required_fields():
    r = await marine_admiralty_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=50_000,
    )
    s = r["surveys"][0]
    for k in (
        "id", "title", "start_date", "end_date",
        "spatial_resolution", "data_size_bytes",
        "bbox", "portal_url",
    ):
        assert k in s, f"missing field {k} in survey row"
    assert s["portal_url"].startswith("https://seabed.admiralty.co.uk")


async def test_surveys_are_sorted_newest_first():
    r = await marine_admiralty_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=50_000,
    )
    end_dates = [s["end_date"] or "" for s in r["surveys"]]
    assert end_dates == sorted(end_dates, reverse=True)


async def test_birmingham_inland_returns_zero():
    r = await marine_admiralty_uk(lat=52.4862, lon=-1.8904, radius_m=5000)
    assert "error" not in r
    assert r["count"] == 0


async def test_atlantic_outside_uk_archive_returns_zero():
    # Far Atlantic — well outside ADMIRALTY's UK-focused holdings.
    r = await marine_admiralty_uk(lat=52.0, lon=-20.0, radius_m=5000)
    assert "error" not in r
    assert r["count"] == 0


async def test_aberdeen_offshore_has_surveys():
    r = await marine_admiralty_uk(lat=57.2, lon=-1.5, radius_m=10_000)
    assert "error" not in r
    assert r["count"] >= 1


async def test_radius_capped():
    r = await marine_admiralty_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=500_000,
    )
    assert "error" in r


async def test_invalid_lat_returns_error():
    r = await marine_admiralty_uk(lat=999.0, lon=0.0, radius_m=1000)
    assert "error" in r


async def test_attribution_credits_ukho_and_explains_login():
    r = await marine_admiralty_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=10_000,
    )
    a = r["attribution"]
    assert "Crown copyright" in a
    assert "UK Hydrographic Office" in a or "UKHO" in a
    # Tool must not give the user the impression it'll hand them files.
    assert "metadata only" in a or "registration" in a


async def test_results_cap_50():
    # Use a wide bbox to maximise hits.
    r = await marine_admiralty_uk(
        lat=_DOGGER_LAT, lon=_DOGGER_LON, radius_m=50_000,
    )
    assert len(r["surveys"]) <= 50


# ---------------------------------------------------------------------------
# Helper unit tests (pure functions, no network).
# ---------------------------------------------------------------------------


def test_bbox_overlap_basic():
    a = (0.0, 0.0, 2.0, 2.0)
    b = (1.0, 1.0, 3.0, 3.0)
    assert _bbox_overlap(a, b) is True
    c = (3.0, 3.0, 4.0, 4.0)
    assert _bbox_overlap(a, c) is False


def test_bbox_overlap_touching_edges_count_as_overlap():
    # Adjacent bboxes that share only an edge — depending on convention
    # this is "touching" not "overlapping". Standard SAT treats touching
    # as overlap because all comparisons use strict >. Document that.
    a = (0.0, 0.0, 1.0, 1.0)
    b = (1.0, 0.0, 2.0, 1.0)
    assert _bbox_overlap(a, b) is True


def test_coords_bbox_handles_nested_geojson():
    coords = [[[0.5, 53.0], [0.6, 53.1], [0.55, 53.2]]]
    assert _coords_bbox(coords) == (0.5, 53.0, 0.6, 53.2)


def test_coords_bbox_handles_multipolygon():
    coords = [
        [[[0.5, 53.0], [0.6, 53.1]]],
        [[[1.0, 54.0], [1.5, 54.5]]],
    ]
    assert _coords_bbox(coords) == (0.5, 53.0, 1.5, 54.5)


def test_coords_bbox_empty_returns_none():
    assert _coords_bbox([]) is None
    assert _coords_bbox([[]]) is None


def test_format_resolution_equivalent_scale():
    arr = [{"spatialResolutionType": {"spatialResolutionType": "equivalent scale"},
            "spatialResolution": 137600}]
    assert _format_resolution(arr) == "1:137,600"


def test_format_resolution_distance_metric():
    arr = [{"spatialResolutionType": {"spatialResolutionType": "distance"},
            "spatialResolution": 2.0}]
    assert _format_resolution(arr) == "2 m grid"


def test_format_resolution_distance_fractional():
    arr = [{"spatialResolutionType": {"spatialResolutionType": "distance"},
            "spatialResolution": 0.5}]
    assert _format_resolution(arr) == "0.5 m grid"


def test_format_resolution_inapplicable_returns_none():
    arr = [{"spatialResolutionType": {"spatialResolutionType": "inapplicable"},
            "spatialResolution": 0}]
    assert _format_resolution(arr) is None


def test_format_resolution_empty_or_missing():
    assert _format_resolution(None) is None
    assert _format_resolution([]) is None
