from __future__ import annotations

import html
import logging

from fastmcp import FastMCP
from starlette.middleware import Middleware as ASGIMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from geo_mcp.config import load_settings
from geo_mcp.data_access.postgis import get_pool
from geo_mcp.middleware import AuthMiddleware, UsageLoggingMiddleware
from geo_mcp.signup import start_signup, verify_signup
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
from geo_mcp.tools.property import property_lookup_uk
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
    app.tool(property_lookup_uk)

    @app.custom_route("/", methods=["GET"])
    async def root(_: Request) -> HTMLResponse:
        return HTMLResponse(_PAGE_ROOT)

    @app.custom_route("/signup", methods=["GET"])
    async def signup_form(_: Request) -> HTMLResponse:
        return HTMLResponse(_PAGE_SIGNUP_FORM)

    @app.custom_route("/signup", methods=["POST"])
    async def signup_submit(request: Request) -> HTMLResponse:
        form = await request.form()
        email = str(form.get("email") or "").strip()
        # Naive honeypot field — bots fill it, humans don't see it.
        if form.get("hp"):
            return HTMLResponse(_PAGE_SIGNUP_SENT, status_code=200)
        if not email or "@" not in email or len(email) > 254:
            return HTMLResponse(_page_error("Please enter a valid email address."), status_code=400)
        if not _rate_limit_allow(request):
            return HTMLResponse(
                _page_error("Too many signups from this address. Try again in an hour."),
                status_code=429,
            )
        try:
            await start_signup(email, source_ip=_client_ip(request))
        except ValueError:
            return HTMLResponse(_page_error("Please enter a valid email address."), status_code=400)
        except Exception:
            log.exception("signup failed")
            return HTMLResponse(_page_error("Something went wrong. Please try again."), status_code=500)
        return HTMLResponse(_PAGE_SIGNUP_SENT)

    @app.custom_route("/signup/verify", methods=["GET"])
    async def signup_verify(request: Request) -> HTMLResponse:
        token = request.query_params.get("token", "")
        result = await verify_signup(token)
        if result is None:
            return HTMLResponse(_page_error(
                "This confirmation link is invalid or has expired. "
                "Please sign up again."), status_code=400)
        return HTMLResponse(_page_signup_success(result.email, result.api_key))

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


# ---------------------------------------------------------------------------
# Minimal HTML pages for the self-service signup flow.
# Kept inline (rather than a templating engine) to avoid a dependency. If
# this grows past half a dozen pages, pull Jinja2 in.
# ---------------------------------------------------------------------------

_CSS = """\
  :root { color-scheme: light dark; }
  body { font: 16px/1.5 system-ui, -apple-system, sans-serif; max-width: 640px;
         margin: 4em auto; padding: 0 1em; }
  h1 { margin-bottom: .25em; }
  .sub { color: #666; margin-top: 0; }
  input[type=email] { padding: .6em .75em; width: 100%; font-size: 1em;
                      border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; }
  button { padding: .6em 1.2em; font-size: 1em; border: 0; border-radius: 6px;
           background: #1b6ef3; color: white; cursor: pointer; margin-top: .75em; }
  button:hover { background: #1557c0; }
  .hp { position: absolute; left: -9999px; }
  pre { background: #f4f4f4; padding: 1em; border-radius: 6px; overflow-x: auto;
        font-size: .9em; }
  .key { font-family: ui-monospace, monospace; word-break: break-all; }
  .notice { background: #fff3cd; border: 1px solid #ffe69c; padding: .75em 1em;
            border-radius: 6px; margin: 1em 0; }
  @media (prefers-color-scheme: dark) {
    pre { background: #1e1e1e; } .notice { background: #3a2f00; border-color: #6b5800; }
  }
"""


def _wrap(title: str, body: str) -> str:
    return (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head>"
        f"<body>{body}</body></html>"
    )


_PAGE_ROOT = _wrap("geo-mcp", """
  <h1>geo-mcp</h1>
  <p class="sub">UK-specialist geospatial MCP server — 21 tools for flood risk,
    property history, listed buildings, elevation, geocoding and more.</p>
  <p><a href="/signup">Get a free API key</a> ·
     <a href="https://github.com/pyramid146/geo-mcp">Source on GitHub</a> ·
     <a href="/health">Health</a></p>
""")


_PAGE_SIGNUP_FORM = _wrap("Sign up — geo-mcp", """
  <h1>Get a free API key</h1>
  <p class="sub">Enter your email. We'll send a confirmation link; clicking it
    reveals your key exactly once.</p>
  <form method="POST" action="/signup">
    <input class="hp" type="text" name="hp" tabindex="-1" autocomplete="off">
    <label for="email">Email</label>
    <input id="email" name="email" type="email" required autofocus>
    <br><button type="submit">Send confirmation email</button>
  </form>
""")


_PAGE_SIGNUP_SENT = _wrap("Check your email — geo-mcp", """
  <h1>Check your email</h1>
  <p>If that address is valid, a confirmation link is on its way.
     It expires in 24 hours.</p>
  <p>Didn't get it? Check your spam folder, then <a href="/signup">try again</a>.</p>
""")


def _page_signup_success(email: str, api_key: str) -> str:
    import os as _os
    base = _os.getenv("GEO_MCP_PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    mcp_url = f"{base}/mcp"
    body = f"""
  <h1>You're in</h1>
  <p class="sub">Account: <code>{html.escape(email)}</code></p>
  <div class="notice">
    <strong>Save this key now.</strong> It's shown exactly once — we only
    store its hash. If you lose it, sign up again to mint a new one.
  </div>
  <p class="key"><code>{html.escape(api_key)}</code></p>
  <h2>Use it</h2>
  <p>Add this to your MCP client config (example for Claude Code
     <code>~/.claude/mcp_servers.json</code>):</p>
  <pre>{{
  "geo-mcp": {{
    "type": "http",
    "url": "{html.escape(mcp_url)}",
    "headers": {{ "Authorization": "Bearer {html.escape(api_key)}" }}
  }}
}}</pre>
"""
    return _wrap("Your geo-mcp API key", body)


def _page_error(message: str) -> str:
    return _wrap("geo-mcp", f"""
  <h1>Hmm.</h1>
  <p>{html.escape(message)}</p>
  <p><a href="/signup">Back to signup</a></p>
""")


# ---------------------------------------------------------------------------
# Naive per-IP rate-limiter for /signup. In-memory, process-local — good
# enough for the single-node MVP. Any meaningful horizontal scaling would
# move this to Postgres or Redis.
# ---------------------------------------------------------------------------

import time as _time  # noqa: E402

_RATE_LIMIT_MAX = 5          # signups per IP
_RATE_LIMIT_WINDOW_S = 3600  # per hour
_rate_hits: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limit_allow(request: Request) -> bool:
    ip = _client_ip(request)
    now = _time.time()
    hits = [t for t in _rate_hits.get(ip, []) if now - t < _RATE_LIMIT_WINDOW_S]
    if len(hits) >= _RATE_LIMIT_MAX:
        _rate_hits[ip] = hits
        return False
    hits.append(now)
    _rate_hits[ip] = hits
    return True


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
