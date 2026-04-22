"""Cached pyproj transformers for the common UK CRS pairs.

Every tool that crosses EPSG:4326 ↔ EPSG:27700 was building its own
``pyproj.Transformer`` — cheap individually but duplicated across
~9 modules. One cached transformer per pair here; use via
``to_osgb()`` / ``to_wgs84()`` in tool code.
"""
from __future__ import annotations

from functools import lru_cache

from pyproj import Transformer


@lru_cache(maxsize=1)
def to_osgb() -> Transformer:
    """WGS84 lon/lat → OSGB36 easting/northing (EPSG:4326 → EPSG:27700)."""
    return Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)


@lru_cache(maxsize=1)
def to_wgs84() -> Transformer:
    """OSGB36 easting/northing → WGS84 lon/lat (EPSG:27700 → EPSG:4326)."""
    return Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
