"""UPRN-based property lookup.

One tool: ``property_lookup_uk(uprn)``. Given a Unique Property Reference
Number, returns the canonical coordinate anchor (WGS84 + OSGB) plus the
full admin hierarchy you'd get from ``reverse_geocode_uk``. It's the
bridge between "UPRN sitting in a caller's database" and a point on a
map that every other tool in this server can work with.

Source: OS Open UPRN (OGLv3). No addresses — OS Open UPRN is deliberately
geometry-only.
"""
from __future__ import annotations

from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools.geocoding import reverse_geocode_uk

_ATTRIBUTION = (
    "Contains OS data © Crown copyright and database right 2026. OS Open "
    "UPRN is licensed under the Open Government Licence v3.0. Admin "
    "hierarchy supplied via ONS (ONSPD) and Ordnance Survey (Boundary-Line), "
    "also under OGLv3."
)


async def property_lookup_uk(uprn: int | str) -> dict[str, Any]:
    """Resolve a UK Unique Property Reference Number (UPRN) to a
    coordinate + admin hierarchy.

    Every addressable location in Great Britain has a UPRN — a stable
    12-digit identifier assigned by Ordnance Survey / local authorities.
    This tool is the canonical "place this UPRN on a map" resolver,
    backed by the OS Open UPRN dataset (~41.5M GB UPRNs, OGLv3).

    Once you have the returned ``lat, lon``, chain into any other tool
    that takes coordinates — ``flood_assessment_uk``, ``heritage_nearby_uk``,
    ``geology_uk``, ``elevation``, etc.

    What this tool **does not** return: an address. OS Open UPRN is
    geometry-only; address-level data (house number, street, town) is
    only available through commercially-licensed AddressBase products.
    For property details we can surface, chain into:
      * ``energy_performance_uk(uprn=...)`` — EPC address + property type +
        energy rating, when an EPC has been lodged.
      * ``recent_sales_uk(postcode=...)`` — HMLR Price Paid comparables
        in the resolved postcode.

    Coverage is **Great Britain** (England + Scotland + Wales). Northern
    Ireland UPRNs are assigned by LPS, not Ordnance Survey, and aren't
    present in this dataset.

    Arguments:
        uprn: the UPRN as an integer or numeric string. UPRNs are
            positive, up to 12 digits.

    Returns:
        {
          "uprn": 10033544614,
          "lat": 51.50101,
          "lon": -0.14156,
          "osgb": {"easting": 530023.0, "northing": 179957.0},
          "admin": {
              "postcode": "SW1A 2AA",
              "distance_to_postcode_centroid_m": 12.7,
              "country":          {"code": "E92000001", "name": "England"},
              "region":           {"code": "E12000007", "name": "London"},
              "local_authority":  {"code": "E09000033", "name": "City of Westminster"},
              "ward":             {"code": "...",       "name": "..."},
              "lsoa":             {"code": "...",       "name": null},
              "msoa":             {"code": "...",       "name": null},
              "geology":          {...},
          },
          "source": "OS Open UPRN",
          "attribution": "..."
        }

    On invalid or unknown UPRN returns ``{"error": ..., "message": ...}``.
    """
    s = str(uprn).strip()
    if not s.isdigit():
        return {"error": "invalid_uprn", "message": f"UPRN must be numeric, got {uprn!r}."}
    if not 1 <= len(s) <= 12:
        return {"error": "invalid_uprn", "message": "UPRN must be 1–12 digits."}

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT uprn, easting, northing, lat, lon
              FROM staging.os_open_uprn
             WHERE uprn = $1
            """,
            int(s),
        )

    if row is None:
        return {
            "error": "uprn_not_found",
            "message": (
                f"UPRN {s} not in OS Open UPRN. Either it doesn't exist, "
                f"is Northern Irish (LPS-assigned, out of coverage), or "
                f"the dataset is older than the UPRN's assignment date."
            ),
        }

    lat = float(row["lat"])
    lon = float(row["lon"])

    # Admin hierarchy + geology, via the same code path as reverse_geocode_uk.
    # Graceful fallback to a minimal response if that lookup fails — a bad
    # ONSPD join shouldn't make the UPRN resolve itself unreachable.
    try:
        rg = await reverse_geocode_uk(lat=lat, lon=lon)
        admin = rg if "error" not in rg else None
    except Exception:
        admin = None

    return {
        "uprn": int(row["uprn"]),
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "osgb": {
            "easting":  round(float(row["easting"]), 2),
            "northing": round(float(row["northing"]), 2),
        },
        "admin": admin,
        "source": "OS Open UPRN",
        "attribution": _ATTRIBUTION,
    }
