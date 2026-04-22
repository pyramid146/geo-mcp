from __future__ import annotations

import logging

from fastmcp import FastMCP
from starlette.middleware import Middleware as ASGIMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from geo_mcp.config import load_settings
from geo_mcp.data_access.postgis import get_pool
from geo_mcp.middleware import AuthMiddleware, UsageLoggingMiddleware
from geo_mcp.tools.boreholes import boreholes_nearby_uk
from geo_mcp.tools.distance import distance_between
from geo_mcp.tools.elevation import elevation
from geo_mcp.tools.elevation_summary import elevation_summary_uk
from geo_mcp.tools.epc import energy_performance_uk
from geo_mcp.tools.flood import flood_risk_uk
from geo_mcp.tools.flood_assessment import flood_assessment_uk
from geo_mcp.tools.flood_historic import historic_floods_uk
from geo_mcp.tools.flood_planning import nppf_planning_context_uk
from geo_mcp.tools.flood_probability import flood_risk_probability_uk
from geo_mcp.tools.flood_re import flood_re_eligibility_uk
from geo_mcp.tools.flood_summary import flood_risk_summary_uk
from geo_mcp.tools.flood_surface_water import surface_water_risk_uk
from geo_mcp.tools.forward_geocoding import geocode_uk
from geo_mcp.tools.geocoding import reverse_geocode_uk
from geo_mcp.tools.geology import geology_uk
from geo_mcp.tools.heritage import heritage_nearby_uk, is_listed_building_uk
from geo_mcp.tools.price_paid import recent_sales_uk
from geo_mcp.tools.transforms import transform_coords

log = logging.getLogger("geo_mcp")


def build_app() -> FastMCP:
    app = FastMCP(name="geo-mcp")
    app.add_middleware(UsageLoggingMiddleware())
    app.tool(transform_coords)
    app.tool(distance_between)
    app.tool(geocode_uk)
    app.tool(reverse_geocode_uk)
    app.tool(flood_risk_uk)
    app.tool(flood_risk_probability_uk)
    app.tool(historic_floods_uk)
    app.tool(surface_water_risk_uk)
    app.tool(flood_risk_summary_uk)
    app.tool(nppf_planning_context_uk)
    app.tool(flood_re_eligibility_uk)
    app.tool(flood_assessment_uk)
    app.tool(elevation)
    app.tool(elevation_summary_uk)
    app.tool(geology_uk)
    app.tool(boreholes_nearby_uk)
    app.tool(is_listed_building_uk)
    app.tool(heritage_nearby_uk)
    app.tool(recent_sales_uk)
    app.tool(energy_performance_uk)

    @app.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        """Liveness + readiness probe. Unauthenticated (bypassed in AuthMiddleware)."""
        postgres_ok = False
        meta_rows: dict[str, int | None] = {"customers": None, "api_keys": None, "usage_log": None}
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute("SELECT 1")
                for table in meta_rows:
                    meta_rows[table] = await conn.fetchval(f"SELECT COUNT(*) FROM meta.{table}")
            postgres_ok = True
        except Exception:
            log.exception("/health: postgres probe failed")

        tools = await app.list_tools()
        body = {
            "status": "ok" if postgres_ok else "degraded",
            "postgres": postgres_ok,
            "tools": len(tools),
            "meta_rows": meta_rows,
        }
        return JSONResponse(body, status_code=200 if postgres_ok else 503)

    return app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    log.info("geo-mcp starting on http://%s:%d/mcp", settings.http_host, settings.http_port)
    app = build_app()
    app.run(
        transport="http",
        host=settings.http_host,
        port=settings.http_port,
        middleware=[ASGIMiddleware(AuthMiddleware)],
    )


if __name__ == "__main__":
    main()
