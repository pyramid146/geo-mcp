from __future__ import annotations

import pytest

from geo_mcp.tools.transforms import transform_coords

pytestmark = pytest.mark.asyncio


async def test_wgs84_to_osgb_london():
    # Central London, roughly Charing Cross
    result = await transform_coords(x=-0.1276, y=51.5074, from_epsg=4326, to_epsg=27700)

    assert "error" not in result
    assert result["units"] == "metre"
    assert "1936" in result["datum"]  # Ordnance Survey of Great Britain 1936
    # British National Grid at Charing Cross ~ (530042, 180380)
    assert result["x"] == pytest.approx(530042, abs=5)
    assert result["y"] == pytest.approx(180380, abs=5)


async def test_osgb_to_wgs84_roundtrip():
    # Round-trip: transform to WGS84 then back and expect near-identity.
    initial = {"x": 530042.6, "y": 180380.5}
    forward = await transform_coords(
        x=initial["x"], y=initial["y"], from_epsg=27700, to_epsg=4326
    )
    back = await transform_coords(
        x=forward["x"], y=forward["y"], from_epsg=4326, to_epsg=27700
    )

    assert back["x"] == pytest.approx(initial["x"], abs=0.1)
    assert back["y"] == pytest.approx(initial["y"], abs=0.1)
    assert forward["units"] == "degree"


async def test_invalid_epsg_returns_error():
    result = await transform_coords(x=0, y=0, from_epsg=999999, to_epsg=4326)
    assert result["error"] == "invalid_epsg"
    assert "message" in result


async def test_out_of_domain_returns_error_or_value():
    # Central Australia is outside OSGB's area of use. pyproj may return inf
    # (which we trap) or a numerically meaningless value — either way, the
    # tool should not raise into the caller.
    result = await transform_coords(
        x=134.0, y=-25.0, from_epsg=4326, to_epsg=27700
    )
    # Either an explicit error, or a finite but meaningless value; must not raise.
    assert isinstance(result, dict)
