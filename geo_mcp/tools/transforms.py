from __future__ import annotations

from typing import Any

from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError, ProjError


async def transform_coords(
    x: float,
    y: float,
    from_epsg: int,
    to_epsg: int,
) -> dict[str, Any]:
    """Convert a 2D coordinate from one coordinate reference system (CRS) to another.

    Use this when a caller provides coordinates in one datum/projection and you
    need them in another — typically between WGS84 longitude/latitude
    (EPSG:4326) and OSGB36 / British National Grid (EPSG:27700) when working
    with UK data.

    Axis order is X first, then Y. For geographic CRSs such as EPSG:4326 that
    means (longitude, latitude), not the common "lat, lon" convention. For
    projected CRSs such as EPSG:27700 that means (easting, northing) in
    metres.

    Common UK-relevant EPSG codes:
      4326   WGS84 longitude / latitude (degrees, global)
      27700  OSGB36 / British National Grid (metres, UK)
      4258   ETRS89 longitude / latitude (degrees, Europe)
      3857   Web Mercator (metres, web map tiles)

    Returns the transformed coordinate plus the target CRS's units and datum
    so the caller can verify what they received. If the EPSG code is invalid
    or the input lies outside the source CRS's area of use, returns an error
    object (not an exception).
    """
    try:
        source = CRS.from_epsg(from_epsg)
        target = CRS.from_epsg(to_epsg)
    except CRSError as exc:
        return {
            "error": "invalid_epsg",
            "message": f"Could not resolve EPSG code: {exc}",
        }

    try:
        transformer = Transformer.from_crs(source, target, always_xy=True)
        x_out, y_out = transformer.transform(x, y)
    except ProjError as exc:
        return {
            "error": "transform_failed",
            "message": str(exc),
        }

    if not (_is_finite(x_out) and _is_finite(y_out)):
        return {
            "error": "out_of_domain",
            "message": (
                f"Input ({x}, {y}) in EPSG:{from_epsg} has no defined projection "
                f"in EPSG:{to_epsg} — likely outside the target CRS's area of use."
            ),
        }

    axis = target.axis_info[0]
    datum = target.datum.name if target.datum else "unknown"

    return {
        "x": x_out,
        "y": y_out,
        "units": axis.unit_name,
        "datum": datum,
        "from_epsg": from_epsg,
        "to_epsg": to_epsg,
        # No dataset attribution — this is a pure projection operation
        # via pyproj. Explicit so every tool response follows the same
        # attribution-field convention.
        "attribution": "Computation via pyproj (Proj/PROJ coordinate transforms).",
    }


def _is_finite(v: float) -> bool:
    return v == v and v not in (float("inf"), float("-inf"))
