"""Shared input-validation helpers used by the tool layer.

Every tool that accepts a WGS84 point, a UK postcode, or a radius
ended up re-implementing the same validations — with slightly
different wording — which is exactly the drift the security audit
flagged. Consolidating here so a fix in one place covers all tools.
"""
from __future__ import annotations

import re
from typing import Any

_POSTCODE_RE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}$", re.IGNORECASE)


def validate_wgs84(lat: float, lon: float) -> dict[str, Any] | None:
    """Return an error dict if lat/lon is outside WGS84 ranges, else None.

    Tool convention: if this returns a dict, the caller returns it
    unchanged to the MCP caller. If None, the inputs are usable.
    """
    if not isinstance(lat, (int, float)) or not (-90.0 <= lat <= 90.0):
        return {"error": "invalid_lat", "message": f"Latitude must be in [-90, 90], got {lat!r}."}
    if not isinstance(lon, (int, float)) or not (-180.0 <= lon <= 180.0):
        return {"error": "invalid_lon", "message": f"Longitude must be in [-180, 180], got {lon!r}."}
    return None


def is_valid_uk_postcode(q: str) -> bool:
    """True if the string parses as a UK postcode (outward + inward parts).

    Spaced or unspaced, case-insensitive. This is a format check, not a
    real-postcode check — ``ZZ99 9ZZ`` passes the regex but isn't in
    ONSPD.
    """
    return isinstance(q, str) and bool(_POSTCODE_RE.match(q.strip()))


def canonical_spaced_postcode(q: str) -> str:
    """Normalise a UK postcode to the ONSPD ``pcds`` form: uppercase,
    single space before the three-char inward code.

    ``sw1a1aa`` and ``SW1A 1AA`` both return ``SW1A 1AA``. Strings
    shorter than 5 chars are returned uppercased as-is (caller should
    have run ``is_valid_uk_postcode`` first).
    """
    s = q.replace(" ", "").upper()
    return f"{s[:-3]} {s[-3:]}" if len(s) >= 5 else s


def validate_radius_m(
    radius_m: int | float,
    *,
    max_m: int,
    min_m: int = 1,
) -> dict[str, Any] | None:
    """Return an error dict if radius is outside [min_m, max_m], else None."""
    if not isinstance(radius_m, (int, float)) or radius_m < min_m or radius_m > max_m:
        return {
            "error": "invalid_radius",
            "message": f"radius_m must be between {min_m} and {max_m}, got {radius_m!r}.",
        }
    return None
