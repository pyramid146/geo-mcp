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
from geo_mcp.tools.property import property_lookup_uk, property_report_uk
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
    app.tool(property_report_uk)

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
# HTML page templates for the self-service signup flow.
# All inline (CSS + SVG + minimal JS) so the server is a single Python
# file with no static-asset pipeline. If this grows past ten pages, pull
# Jinja2 + a real asset tree in.
# ---------------------------------------------------------------------------

# Stylised fantasy-map landmass + offshore islands, outline-only.
# Deliberately not any real-world coastline; just an evocative silhouette.
# vector-effect="non-scaling-stroke" keeps the stroke weight visually
# consistent whether the SVG renders at 22px (header) or 420px (hero).
_UK_SVG = """\
<svg viewBox="0 0 100 130" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"
     fill="none" stroke="currentColor" stroke-width="2"
     stroke-linejoin="round" stroke-linecap="round"
     vector-effect="non-scaling-stroke">
  <path vector-effect="non-scaling-stroke" d="
    M 62 6
    L 57 16
    L 64 22
    C 60 30, 50 30, 42 24
    L 34 30
    C 24 32, 18 44, 28 50
    L 22 58
    C 16 70, 24 80, 32 82
    L 26 94
    C 34 100, 42 98, 48 102
    L 44 114
    L 54 112
    L 60 106
    L 68 108
    C 80 104, 88 94, 84 82
    L 92 72
    C 96 62, 90 50, 82 44
    L 88 32
    L 78 30
    L 74 22
    L 68 18
    Z
  "/>
  <path vector-effect="non-scaling-stroke" d="
    M 94 68
    L 97 65
    L 99 69
    L 96 72
    Z
  "/>
  <path vector-effect="non-scaling-stroke" d="
    M 50 120
    L 54 118
    L 57 121
    L 55 124
    L 51 123
    Z
  "/>
  <path vector-effect="non-scaling-stroke" d="
    M 30 106
    L 33 105
    L 34 108
    L 31 109
    Z
  "/>
</svg>
"""

_CSS = """\
  :root {
    color-scheme: light dark;
    --paper: #f6f5f1;
    --paper-soft: #efece4;
    --ink: #14181f;
    --ink-muted: #5a5e67;
    --border: #e0dccf;
    --accent: #0b5d6e;
    --accent-ink: #ffffff;
    --c-flood: #1e6091;
    --c-property: #b06a1f;
    --c-heritage: #7a1f1f;
    --c-ground: #6b5d2b;
    --c-geocoding: #2d5f4a;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --paper: #10141b;
      --paper-soft: #1a1f28;
      --ink: #e8e6e1;
      --ink-muted: #949aa4;
      --border: #2a2f39;
      --accent: #5fbcc8;
      --accent-ink: #062028;
      --c-flood: #65a8d6;
      --c-property: #d89761;
      --c-heritage: #d47475;
      --c-ground: #c3b584;
      --c-geocoding: #71b897;
    }
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    font: 17px/1.55 system-ui, -apple-system, "Segoe UI Variable", "Segoe UI",
          "Helvetica Neue", sans-serif;
    color: var(--ink);
    background: var(--paper);
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  code, pre { font-family: ui-monospace, "SF Mono", "Cascadia Code",
              "Roboto Mono", Menlo, monospace; }
  code { font-size: .93em; }
  pre {
    background: var(--paper-soft);
    border: 1px solid var(--border);
    padding: 1em 1.25em;
    border-radius: 6px;
    overflow-x: auto;
    font-size: .85rem;
    line-height: 1.55;
    margin: 1rem 0;
  }
  .container { max-width: 68rem; margin: 0 auto; padding: 0 1.5rem; }
  .container-narrow { max-width: 40rem; margin: 0 auto; padding: 0 1.5rem; }

  /* Header */
  .site-header {
    border-bottom: 1px solid var(--border);
    padding: 1rem 0;
  }
  .site-header .container {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }
  .logo {
    display: inline-flex;
    align-items: center;
    gap: .55em;
    font-weight: 700;
    font-size: 1.05rem;
    letter-spacing: -0.02em;
    color: var(--ink);
  }
  .logo:hover { text-decoration: none; }
  .logo svg { width: 22px; height: 28px; color: var(--accent); display: block; }
  .site-nav a {
    color: var(--ink-muted);
    margin-left: 1.5rem;
    font-size: .92em;
  }
  .site-nav a:hover { color: var(--ink); text-decoration: none; }

  /* Hero */
  .hero {
    padding: 4.5rem 0 3rem;
    position: relative;
    overflow: hidden;
  }
  .hero-bg {
    position: absolute;
    right: 1rem;
    top: 1rem;
    opacity: 0.22;
    pointer-events: none;
    color: var(--ink-muted);
  }
  .hero-bg svg {
    width: clamp(180px, 30vw, 340px);
    height: auto;
    display: block;
  }
  @media (prefers-color-scheme: dark) {
    .hero-bg { opacity: 0.3; }
  }
  @media (max-width: 780px) {
    .hero-bg { display: none; }
  }
  .hero h1 {
    font-size: clamp(2.1rem, 5vw, 3.25rem);
    line-height: 1.1;
    letter-spacing: -0.025em;
    margin: 0 0 .5em;
    max-width: 22ch;
    position: relative;
  }
  .hero .sub {
    font-size: 1.1rem;
    color: var(--ink-muted);
    max-width: 54ch;
    margin: 0 0 1.5rem;
    position: relative;
  }
  .hero-ctas { position: relative; margin-top: 1.75rem; }

  /* Buttons */
  .btn {
    display: inline-flex;
    align-items: center;
    padding: .75em 1.35em;
    background: var(--accent);
    color: var(--accent-ink);
    border-radius: 6px;
    border: 0;
    cursor: pointer;
    font: inherit;
    font-weight: 500;
    text-decoration: none;
    font-size: 1rem;
  }
  .btn:hover { opacity: 0.92; text-decoration: none; }
  .btn-ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--border);
    margin-left: .5rem;
  }

  /* Section headings */
  h2 {
    font-size: 1.5rem;
    letter-spacing: -0.015em;
    margin: 3rem 0 1.25rem;
  }
  .section-lead {
    color: var(--ink-muted);
    margin: 0 0 1.75rem;
    max-width: 60ch;
  }

  /* Domain prompt cards */
  .prompt-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 1rem;
    margin: 0 0 3rem;
  }
  .prompt-card {
    border: 1px solid var(--border);
    border-left: 4px solid var(--domain, var(--ink));
    border-radius: 4px;
    padding: 1.1rem 1.35rem 1.25rem;
    background: var(--paper);
  }
  .prompt-card h3 {
    margin: 0 0 .75rem;
    font-size: .72rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--domain);
    font-weight: 600;
  }
  .prompt-card ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .prompt-card li {
    margin: .45rem 0;
    font-size: .94rem;
    line-height: 1.45;
    color: var(--ink);
  }
  .prompt-card li::before {
    content: "“";
    color: var(--domain);
    font-weight: 700;
    margin-right: .1em;
  }
  .prompt-card li::after {
    content: "”";
    color: var(--domain);
    font-weight: 700;
    margin-left: .1em;
  }

  /* Forms */
  form { margin: 1.5rem 0 0; }
  label {
    display: block;
    font-weight: 500;
    font-size: .9rem;
    color: var(--ink-muted);
    margin-bottom: .4rem;
  }
  input[type=email] {
    padding: .75rem 1rem;
    width: 100%;
    font: inherit;
    font-size: 1rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--paper);
    color: var(--ink);
  }
  input[type=email]:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(11, 93, 110, 0.18);
  }
  .form-actions { margin-top: 1rem; }
  .form-hint {
    margin-top: 1rem;
    font-size: .88rem;
    color: var(--ink-muted);
  }
  .hp { position: absolute; left: -9999px; }

  /* Key display + copy */
  .notice {
    padding: .9rem 1.1rem;
    border-radius: 6px;
    background: rgba(176, 106, 31, 0.08);
    color: var(--ink);
    border-left: 3px solid var(--c-property);
    margin: 1.25rem 0;
    font-size: .95rem;
  }
  .key-wrap {
    position: relative;
    margin: 1rem 0 1.5rem;
  }
  .key-box {
    padding: 1rem 1.25rem;
    padding-right: 5.5rem;
    background: var(--paper-soft);
    border: 1px solid var(--border);
    border-radius: 6px;
    font-family: ui-monospace, "SF Mono", "Cascadia Code", Menlo, monospace;
    font-size: 0.95rem;
    word-break: break-all;
    line-height: 1.45;
  }
  .copy-btn {
    position: absolute;
    right: .75rem;
    top: 50%;
    transform: translateY(-50%);
    padding: .4em .8em;
    background: var(--ink);
    color: var(--paper);
    border: 0;
    border-radius: 4px;
    cursor: pointer;
    font-size: .82rem;
    font-family: inherit;
  }
  .copy-btn.copied { background: var(--c-geocoding); }

  /* Footer */
  .site-footer {
    margin-top: 4rem;
    border-top: 1px solid var(--border);
    padding: 1.5rem 0 2rem;
    color: var(--ink-muted);
    font-size: .88rem;
  }
  .site-footer .container {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem 1.5rem;
    justify-content: space-between;
  }
"""


def _shell(title: str, body: str, *, include_copy_js: bool = False) -> str:
    """Base HTML shell: shared header, main slot, footer."""
    copy_js = ""
    if include_copy_js:
        copy_js = """
<script>
document.addEventListener('click', e => {
  const btn = e.target.closest('.copy-btn');
  if (!btn) return;
  const target = document.getElementById(btn.dataset.target);
  if (!target) return;
  navigator.clipboard.writeText(target.textContent.trim()).then(() => {
    const original = btn.textContent;
    btn.textContent = 'Copied';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = original; btn.classList.remove('copied'); }, 1800);
  });
});
</script>"""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<header class="site-header">
  <div class="container">
    <a class="logo" href="/">{_UK_SVG}<span>geo-mcp</span></a>
    <nav class="site-nav">
      <a href="/signup">Sign up</a>
      <a href="/health">Health</a>
    </nav>
  </div>
</header>
<main>
{body}
</main>
<footer class="site-footer">
  <div class="container">
    <span>UK open-data MCP server · OGLv3 · MIT-licensed code</span>
    <span>geomcp.dev</span>
  </div>
</footer>{copy_js}
</body>
</html>"""


# Backwards-compat wrapper (some older callers still use it; no-op harm).
def _wrap(title: str, body: str) -> str:
    return _shell(title, f'<div class="container-narrow"><div class="hero">{body}</div></div>')


_PAGE_ROOT = _shell("geo-mcp — UK geospatial for LLM agents", """
<div class="container">
  <section class="hero">
    <div class="hero-bg">""" + _UK_SVG + """</div>
    <h1>UK geospatial data, made for LLM agents.</h1>
    <p class="sub">22 tools covering flood risk, property records, heritage,
      geology, elevation, and geocoding — all built on UK open-data sources
      (ONS, Ordnance Survey, Environment Agency, Historic England, BGS,
      HMLR, MHCLG). Returns decisions an LLM can act on, not raw polygons.</p>
    <div class="hero-ctas">
      <a class="btn" href="/signup">Get a free API key</a>
      <a class="btn btn-ghost" href="/health">Service status</a>
    </div>
  </section>

  <h2>What an agent can ask</h2>
  <p class="section-lead">Once connected, an agent can answer questions
  it otherwise can't — grounded in current, attributable UK open data.</p>

  <div class="prompt-grid">
    <div class="prompt-card" style="--domain: var(--c-flood);">
      <h3>Flood</h3>
      <ul>
        <li>What's the flood risk at GL20 5BY, and has it actually flooded before?</li>
        <li>Is this postcode in Flood Zone 2 or 3 for planning?</li>
        <li>Would this property be eligible for Flood Re?</li>
      </ul>
    </div>
    <div class="prompt-card" style="--domain: var(--c-property);">
      <h3>Property</h3>
      <ul>
        <li>Give me a full property report for UPRN 10033544614.</li>
        <li>What have flats sold for in SW1A 1AA in the last 5 years?</li>
        <li>What's the EPC rating and construction age of this property?</li>
      </ul>
    </div>
    <div class="prompt-card" style="--domain: var(--c-heritage);">
      <h3>Heritage &amp; planning</h3>
      <ul>
        <li>Is 10 Downing Street a listed building?</li>
        <li>Scheduled monuments within 500 m of this coordinate?</li>
        <li>Can a new dwelling be built here under NPPF?</li>
      </ul>
    </div>
    <div class="prompt-card" style="--domain: var(--c-ground);">
      <h3>Ground &amp; elevation</h3>
      <ul>
        <li>What's the bedrock at 51.5014, -0.1419?</li>
        <li>Any BGS boreholes within 1 km of this point?</li>
        <li>What's the elevation profile for this postcode area?</li>
      </ul>
    </div>
    <div class="prompt-card" style="--domain: var(--c-geocoding);">
      <h3>Geocoding</h3>
      <ul>
        <li>Where is SW1A 1AA?</li>
        <li>What postcode is closest to these coordinates?</li>
        <li>Convert these British National Grid coordinates to WGS84.</li>
      </ul>
    </div>
  </div>
</div>
""")


_PAGE_SIGNUP_FORM = _shell("Get an API key — geo-mcp", """
<div class="container-narrow">
  <section class="hero">
    <h1>Get a free API key</h1>
    <p class="sub">Enter your email. We'll send a confirmation link;
       clicking it reveals your key exactly once.</p>
    <form method="POST" action="/signup">
      <input class="hp" type="text" name="hp" tabindex="-1" autocomplete="off">
      <label for="email">Email</label>
      <input id="email" name="email" type="email" required autofocus
             placeholder="you@example.com">
      <div class="form-actions">
        <button class="btn" type="submit">Send confirmation email</button>
      </div>
    </form>
    <p class="form-hint">We email your key once and only use your
       address to let you revoke or re-mint it. No marketing.</p>
  </section>
</div>
""")


_PAGE_SIGNUP_SENT = _shell("Check your email — geo-mcp", """
<div class="container-narrow">
  <section class="hero">
    <h1>Check your email</h1>
    <p class="sub">If that address is valid, a confirmation link is on
       its way. It expires in 24 hours.</p>
    <p>Didn't get it? Check your spam folder, then
       <a href="/signup">try again</a>.</p>
  </section>
</div>
""")


def _page_signup_success(email: str, api_key: str) -> str:
    import os as _os
    base = _os.getenv("GEO_MCP_PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    mcp_url = f"{base}/mcp"
    body = f"""
<div class="container-narrow">
  <section class="hero">
    <h1>You're in</h1>
    <p class="sub">Account: <code>{html.escape(email)}</code></p>
    <div class="notice">
      <strong>Save this key now.</strong> It's shown exactly once — we only
      store its hash. If you lose it, sign up again and we'll mint a new one.
    </div>
    <div class="key-wrap">
      <div class="key-box" id="api-key">{html.escape(api_key)}</div>
      <button class="copy-btn" data-target="api-key" type="button">Copy</button>
    </div>
    <h2>Use it</h2>
    <p>Add this to your MCP client config (example for Claude Code at
       <code>~/.claude/mcp_servers.json</code>):</p>
    <pre>{{
  "geo-mcp": {{
    "type": "http",
    "url": "{html.escape(mcp_url)}",
    "headers": {{ "Authorization": "Bearer {html.escape(api_key)}" }}
  }}
}}</pre>
    <p class="form-hint">Restart your MCP client for the new server to be
       discovered. Claude Desktop usually needs a full quit + relaunch.</p>
  </section>
</div>
"""
    return _shell("Your geo-mcp API key", body, include_copy_js=True)


def _page_error(message: str) -> str:
    return _shell("Something went wrong — geo-mcp", f"""
<div class="container-narrow">
  <section class="hero">
    <h1>Hmm.</h1>
    <p class="sub">{html.escape(message)}</p>
    <p><a class="btn btn-ghost" href="/signup">Back to signup</a></p>
  </section>
</div>
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
