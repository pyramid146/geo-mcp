"""Unit tests for geo_mcp.tools._validators."""
from __future__ import annotations

from geo_mcp.tools._validators import (
    canonical_spaced_postcode,
    is_valid_uk_postcode,
    validate_radius_m,
    validate_wgs84,
)


# ---------------------------------------------------------------------------
# validate_wgs84
# ---------------------------------------------------------------------------


def test_valid_wgs84_returns_none():
    assert validate_wgs84(51.5014, -0.1419) is None


def test_out_of_range_lat_rejected():
    r = validate_wgs84(100.0, 0.0)
    assert r["error"] == "invalid_lat"


def test_out_of_range_lon_rejected():
    r = validate_wgs84(0.0, 500.0)
    assert r["error"] == "invalid_lon"


def test_non_numeric_types_rejected():
    assert validate_wgs84("fifty", 0.0)["error"] == "invalid_lat"
    assert validate_wgs84(0.0, None)["error"] == "invalid_lon"


def test_booleans_rejected_even_though_python_treats_bool_as_int():
    # The footgun: Python's bool is a subclass of int, so without the
    # explicit bool check `validate_wgs84(True, False)` would silently
    # treat True as 1 and False as 0 — placing the "point" at null island.
    assert validate_wgs84(True, False)["error"] == "invalid_lat"
    assert validate_wgs84(51.5, True)["error"] == "invalid_lon"


def test_integer_coords_accepted():
    assert validate_wgs84(51, 0) is None


# ---------------------------------------------------------------------------
# validate_radius_m
# ---------------------------------------------------------------------------


def test_valid_radius_returns_none():
    assert validate_radius_m(500, max_m=5000) is None


def test_below_min_radius_rejected():
    assert validate_radius_m(0, max_m=5000)["error"] == "invalid_radius"


def test_above_max_radius_rejected():
    assert validate_radius_m(10_000, max_m=5000)["error"] == "invalid_radius"


def test_bool_radius_rejected():
    # Same footgun as validate_wgs84.
    assert validate_radius_m(True, max_m=5000)["error"] == "invalid_radius"


# ---------------------------------------------------------------------------
# postcode helpers
# ---------------------------------------------------------------------------


def test_uk_postcode_valid_cases():
    assert is_valid_uk_postcode("SW1A 1AA")
    assert is_valid_uk_postcode("sw1a1aa")
    assert is_valid_uk_postcode("M1 1AA")


def test_uk_postcode_invalid_cases():
    assert not is_valid_uk_postcode("not a postcode")
    assert not is_valid_uk_postcode("12345")
    assert not is_valid_uk_postcode("")


def test_canonical_spaced_postcode_normalises():
    assert canonical_spaced_postcode("sw1a1aa") == "SW1A 1AA"
    assert canonical_spaced_postcode("SW1A 1AA") == "SW1A 1AA"
    assert canonical_spaced_postcode(" sw1a 1aa ".strip()) == "SW1A 1AA"
