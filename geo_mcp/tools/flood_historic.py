from __future__ import annotations

import json
from datetime import date
from typing import Any

from geo_mcp.data_access.postgis import get_pool
from geo_mcp.tools._validators import validate_wgs84


def _decode_jsonb(value: Any) -> Any:
    """asyncpg returns jsonb as a JSON string by default; decode to Python."""
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value

_ATTRIBUTION = (
    "Contains Environment Agency data © Environment Agency copyright and/or "
    "database right 2026. Licensed under the Open Government Licence v3.0."
)

# ~1001-01-01 is a sentinel used in the source data for "date unknown".
# Treat anything pre-1800 as null in the outputs so an undated record
# doesn't pollute "earliest event" / "most recent event" numbers.
_MIN_REAL_DATE = date(1800, 1, 1)

_MAX_EVENTS_LISTED = 10

_QUERY = """
WITH pt AS (
    SELECT ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 27700) AS g
),
hits AS (
    SELECT h.name,
           (CASE WHEN h.start_date < $3 THEN NULL ELSE h.start_date END)::date AS start_date,
           (CASE WHEN h.end_date   < $3 THEN NULL ELSE h.end_date   END)::date AS end_date,
           h.flood_src,
           h.flood_caus
      FROM staging.ea_historic_floods h, pt
     WHERE ST_Covers(h.geom, pt.g)
),
aggregates AS (
    SELECT COUNT(*)                                       ::int  AS n_events,
           MIN(start_date) FILTER (WHERE start_date IS NOT NULL) AS earliest,
           MAX(start_date) FILTER (WHERE start_date IS NOT NULL) AS most_recent
      FROM hits
),
by_source AS (
    SELECT flood_src, COUNT(*)::int AS n
      FROM hits GROUP BY flood_src
),
listed AS (
    SELECT name, start_date, end_date, flood_src, flood_caus
      FROM hits
     ORDER BY start_date DESC NULLS LAST
     LIMIT $4
)
SELECT
    (SELECT n_events    FROM aggregates)         AS n_events,
    (SELECT earliest    FROM aggregates)         AS earliest,
    (SELECT most_recent FROM aggregates)         AS most_recent,
    (SELECT jsonb_object_agg(flood_src, n)
       FROM by_source)                           AS by_source,
    (SELECT jsonb_agg(to_jsonb(l))
       FROM listed l)                            AS events;
"""


async def historic_floods_uk(
    lat: float,
    lon: float,
) -> dict[str, Any]:
    """Return recorded historical floods that have actually reached a WGS84 point in England.

    Answers the question "has this location been flooded before, and if so,
    when and from what source?" — the credibility-builder in property risk
    reports. Based on the EA's Recorded Flood Outlines since 1946.

    For each point covered by one or more recorded flood polygons, returns:
      - total number of recorded events covering the point
      - earliest and most-recent event dates (pre-1800 sentinel dates
        stripped — the EA uses 1001-01-01 for undated events)
      - event count by source (main river / sea / ordinary watercourse /
        drainage / sewer / unknown / …)
      - up to 10 most-recent events with their name, window, source, and
        cause (to keep responses bounded when a point is inside many
        overlapping outlines, which happens in Severn and Thames valleys)

    Coverage is **England only**. Welsh / Scottish / NI points return zero
    events — this dataset does not cover them.

    Complements the other flood tools:
      * ``flood_risk_uk`` — planning zones, ignores defences.
      * ``flood_risk_probability_uk`` — RoFRS, insurance-grade, accounts
        for defences.
      * ``historic_floods_uk`` — *has it actually happened here*.

    Arguments:
        lat: WGS84 latitude, -90..90.
        lon: WGS84 longitude, -180..180.

    Returns:
        {
          "count": int,                                    # 0 if never flooded on record
          "earliest": "YYYY-MM-DD" | null,
          "most_recent": "YYYY-MM-DD" | null,
          "by_source": {"main river": int, "sea": int, ...} | {},
          "events": [
            {"name", "start_date", "end_date", "flood_src", "flood_caus"},
            ...  # up to 10 most recent
          ],
          "coverage_note": "England only.",
          "source": "EA Recorded Flood Outlines",
          "attribution": "..."
        }

    On invalid lat/lon, returns ``{"error": ..., "message": ...}``.
    """
    err = validate_wgs84(lat, lon)
    if err is not None:
        return err

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_QUERY, lon, lat, _MIN_REAL_DATE, _MAX_EVENTS_LISTED)

    n = row["n_events"] or 0
    events = _decode_jsonb(row["events"]) or []
    by_source = _decode_jsonb(row["by_source"]) or {}
    return {
        "count": n,
        "earliest": row["earliest"].isoformat() if row["earliest"] else None,
        "most_recent": row["most_recent"].isoformat() if row["most_recent"] else None,
        "by_source": by_source,
        "events": [
            {
                "name": e.get("name"),
                "start_date": e.get("start_date"),
                "end_date": e.get("end_date"),
                "flood_src": e.get("flood_src"),
                "flood_caus": e.get("flood_caus"),
            }
            for e in events
        ],
        "coverage_note": (
            "Dataset covers England only. A zero count does not prove a "
            "point is unflooded — small, old, or unmapped events may be "
            "missing from the Environment Agency's records."
        ),
        "source": "EA Recorded Flood Outlines",
        "attribution": _ATTRIBUTION,
    }
