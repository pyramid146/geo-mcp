"""UPRN-based property lookup + composite property report.

Two tools:

* ``property_lookup_uk(uprn)`` — cheap resolver. UPRN → coords + admin.
  Call this when you want to plug a UPRN into other per-point tools.
* ``property_report_uk(uprn)`` — one-call composite. Runs the resolver
  plus EPC / comparable sales / flood assessment / listed-building +
  heritage / elevation in parallel. The tool a conveyancer / mortgage
  broker / insurance chatbot actually wants.

Source: OS Open UPRN (OGLv3) + chained sub-tools.
"""
from __future__ import annotations

import asyncio
from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools.elevation import elevation
from geo_mcp.tools.epc import energy_performance_uk
from geo_mcp.tools.flood_assessment import flood_assessment_uk
from geo_mcp.tools.geocoding import reverse_geocode_uk
from geo_mcp.tools.heritage import heritage_nearby_uk, is_listed_building_uk
from geo_mcp.tools.price_paid import recent_sales_uk

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


_REPORT_ATTRIBUTION = (
    "Composite view built from multiple UK open-data sources — see each "
    "sub-source block for its own attribution. Underlying sources: OS "
    "Open UPRN, ONSPD, OS Boundary-Line, BGS Geology 625k, OS Terrain 50, "
    "HMLR Price Paid Data, MHCLG EPC Register, Historic England NHLE, "
    "Environment Agency flood datasets. All OGLv3-licensed."
)


async def property_report_uk(uprn: int | str) -> dict[str, Any]:
    """One-call composite property report for a UK UPRN.

    The single tool a property-risk workflow — conveyancer, mortgage
    broker, insurance bot, surveyor — actually wants. Given a UPRN,
    fans out in parallel to:

      * ``property_lookup_uk`` — coords + admin + geology (the anchor)
      * ``energy_performance_uk(uprn=...)`` — latest EPC for the unit
        (property type, age band, rating, Flood Re year signal)
      * ``recent_sales_uk(postcode=...)`` — HMLR Price Paid comparables
        across the postcode (5-year window, stats + recent sales)
      * ``is_listed_building_uk`` — exact-point NHLE check
      * ``heritage_nearby_uk`` — listed buildings / monuments / parks
        within 500m
      * ``flood_assessment_uk`` — composite flood verdict (planning
        zone, RoFRS probabilistic, surface water, historic events,
        NPPF planning status)
      * ``elevation`` — metres above OSGB datum

    Sub-tools run concurrently; one failing doesn't abort the report.
    Missing blocks come back as ``null`` with an ``error`` sibling so
    the caller can distinguish "no EPC" from "EPC lookup crashed".

    Coverage caveats surface per-block:
      * EPC + Price Paid are **England & Wales only**
      * Heritage (NHLE) is **England only**
      * Flood tools are **England only**
      * UPRN resolver is **Great Britain**
      * A Scottish or NI address will resolve via the UPRN but return
        ``coverage_gap`` on the flood / heritage / property blocks

    Latency: typically 500–1500 ms. Dominated by ``flood_assessment_uk``
    (which itself fans out to 5 upstream datasets including a live EA
    WMS call for surface water).

    Arguments:
        uprn: the UPRN as an integer or numeric string. UPRNs are
            positive, up to 12 digits.

    Returns:
        {
          "uprn": 10033544614,
          "headline": "one-sentence plain-English summary",
          "narrative": "multi-sentence summary agent can read verbatim",
          "site": {...from property_lookup_uk: lat/lon/osgb/admin...},
          "epc":       {...from energy_performance_uk | null},
          "sales":     {...from recent_sales_uk | null},
          "listed":    {...from is_listed_building_uk | null},
          "heritage":  {...from heritage_nearby_uk | null},
          "flood":     {...from flood_assessment_uk | null},
          "elevation": {"metres": 12.3 | null},
          "attribution": "..."
        }

    On invalid / unknown UPRN returns ``{"error": ..., "message": ...}``
    (same shape as ``property_lookup_uk``).
    """
    site = await property_lookup_uk(uprn)
    if "error" in site:
        return site

    lat = site["lat"]
    lon = site["lon"]
    admin = site.get("admin") or {}
    postcode = admin.get("postcode")

    async def _safe(coro, label):
        try:
            return await coro
        except Exception as exc:
            return {"error": "subtool_failed", "message": f"{label}: {type(exc).__name__}"}

    epc_task      = _safe(energy_performance_uk(uprn=str(uprn)),             "epc")
    sales_task    = _safe(recent_sales_uk(postcode=postcode),                "sales") \
                    if postcode else asyncio.sleep(0, result=None)
    listed_task   = _safe(is_listed_building_uk(lat=lat, lon=lon),           "listed")
    heritage_task = _safe(heritage_nearby_uk(lat=lat, lon=lon, radius_m=500), "heritage")
    flood_task    = _safe(flood_assessment_uk(postcode=postcode),            "flood") \
                    if postcode else asyncio.sleep(0, result=None)
    elev_task     = _safe(elevation(points=[{"lat": lat, "lon": lon}]),      "elevation")

    epc, sales, listed, heritage, flood, elev = await asyncio.gather(
        epc_task, sales_task, listed_task, heritage_task, flood_task, elev_task,
    )

    elevation_m = _pluck_elevation(elev)
    headline, narrative = _report_narrative(
        uprn=site["uprn"],
        postcode=postcode,
        admin=admin,
        epc=epc,
        sales=sales,
        listed=listed,
        heritage=heritage,
        flood=flood,
        elevation_m=elevation_m,
    )

    return {
        "uprn":       site["uprn"],
        "headline":   headline,
        "narrative":  narrative,
        "site":       site,
        "epc":        epc,
        "sales":      sales,
        "listed":     listed,
        "heritage":   heritage,
        "flood":      flood,
        "elevation":  {"metres": elevation_m},
        "attribution": _REPORT_ATTRIBUTION,
    }


def _pluck_elevation(elev: Any) -> float | None:
    """Extract the single sample's elevation metres from elevation()'s
    batch response shape."""
    if not isinstance(elev, dict) or "error" in elev:
        return None
    samples = elev.get("samples") or elev.get("points") or []
    if not samples:
        return None
    first = samples[0] if isinstance(samples, list) else None
    if not isinstance(first, dict):
        return None
    v = first.get("elevation_m")
    if v is None or first.get("status") not in (None, "ok"):
        return None
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return None


def _report_narrative(
    *,
    uprn: int,
    postcode: str | None,
    admin: dict[str, Any],
    epc: Any,
    sales: Any,
    listed: Any,
    heritage: Any,
    flood: Any,
    elevation_m: float | None,
) -> tuple[str, str]:
    loc_parts: list[str] = []
    la = ((admin or {}).get("admin") or {}).get("local_authority") or {}
    if la.get("name"):
        loc_parts.append(la["name"])
    ctry = ((admin or {}).get("admin") or {}).get("country") or {}
    if ctry.get("name") and ctry["name"] != "England":
        loc_parts.append(ctry["name"])
    loc_phrase = ", ".join(loc_parts) or "this location"
    pc_phrase = f"postcode {postcode}" if postcode else "this UPRN"

    # EPC → property type + age-band + rating
    epc_phrase = ""
    if isinstance(epc, dict) and "error" not in epc and epc.get("property"):
        p = epc["property"]
        ptype = p.get("property_type") or "property"
        built_form = p.get("built_form")
        age = p.get("construction_age_band")
        rating = (p.get("energy_rating") or {}).get("current")
        bits = [f"a {ptype.lower()}"]
        if built_form:
            bits.insert(0, built_form.lower())
        age_phrase = f" ({age})" if age else ""
        rating_phrase = f", EPC rating {rating}" if rating else ""
        epc_phrase = f" It's {' '.join(bits)}{age_phrase}{rating_phrase}."
    elif isinstance(epc, dict) and epc.get("property") is None:
        epc_phrase = " No EPC has been lodged against this UPRN since 2008."

    # Listed building status
    listed_phrase = ""
    if isinstance(listed, dict) and "error" not in listed:
        if listed.get("is_listed"):
            matches = listed.get("matches") or []
            if matches:
                top = matches[0]
                grade = top.get("grade") or ""
                name = top.get("name") or "a listed entry"
                listed_phrase = f" **Listed ({grade})** — {name}."
            else:
                listed_phrase = " Listed (grade not reported)."
        else:
            listed_phrase = " Not a listed building at exact point."

    # Heritage nearby (exclude the listed-building at this point — that's
    # covered above).
    heritage_phrase = ""
    if isinstance(heritage, dict) and "error" not in heritage:
        hc = heritage.get("total", 0) or 0
        if hc:
            heritage_phrase = f" {hc} heritage asset{'s' if hc != 1 else ''} within 500 m."

    # Flood verdict (from flood_assessment_uk)
    flood_phrase = ""
    if isinstance(flood, dict) and "error" not in flood:
        verdict = flood.get("verdict")
        verdict_label = {
            "low":          "low",
            "moderate":     "moderate",
            "high":         "elevated",
            "coverage_gap": "not assessed (dataset is England-only)",
        }.get(verdict, verdict or "unknown")
        flood_phrase = f" Flood risk: **{verdict_label}**."

    # Sales summary (median + count)
    sales_phrase = ""
    if isinstance(sales, dict) and "error" not in sales and sales.get("count"):
        stats = sales.get("stats") or {}
        median = stats.get("median_price")
        cnt = sales.get("count")
        yrs = (sales.get("window") or {}).get("years")
        if median:
            sales_phrase = (
                f" {cnt} recorded sales in {pc_phrase} over the last {yrs}y "
                f"(median £{int(median):,})."
            )

    # Elevation — only mention for 'surprising' values (well above sea level
    # or arguably at-risk low-lying — i.e. anything that'd actually catch a
    # reader's eye). Skip the boring middle.
    elev_phrase = ""
    if elevation_m is not None and (elevation_m < 3 or elevation_m > 150):
        elev_phrase = f" Ground elevation {elevation_m} m AMSL."

    parts = [epc_phrase, listed_phrase, heritage_phrase, flood_phrase, sales_phrase, elev_phrase]
    # Each part already starts with a leading space so sentences join
    # cleanly. strip() cleans the overall output, not internal spacing.
    body = "".join(p for p in parts if p).strip()

    # Headline: a one-liner that leads with the most decision-relevant
    # signal. Listed-building status beats flood risk beats EPC rating —
    # anything that'd change the buy/don't-buy calculus first.
    headline = f"UPRN {uprn} — {loc_phrase}."
    if isinstance(listed, dict) and listed.get("is_listed"):
        headline = f"Listed building in {loc_phrase}."
    elif isinstance(flood, dict) and flood.get("verdict") == "high":
        headline = f"Elevated flood risk in {loc_phrase}."
    elif isinstance(flood, dict) and flood.get("verdict") == "coverage_gap":
        headline = f"Property in {loc_phrase} — flood data England-only, not assessed."

    sep = " " if body else ""
    narrative = f"UPRN {uprn} sits in {loc_phrase}.{sep}{body}".strip()
    return headline, narrative
