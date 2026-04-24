"""HTTP-contract tests for ``AuthMiddleware``.

We drive the middleware against a minimal Starlette app (with a trivial
'hello' route behind it) using ``httpx.ASGITransport`` — so we exercise
the real middleware code path without spinning up a real HTTP server.
Faster than spawning the full FastMCP server, and still proves the
middleware's behaviour end-to-end.
"""
from __future__ import annotations

import uuid

import httpx
import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from geo_mcp.auth import mint_key, revoke_key
from geo_mcp.middleware import AuthMiddleware

pytestmark = pytest.mark.asyncio


def _make_app() -> Starlette:
    async def hello(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return Starlette(
        routes=[
            Route("/mcp", hello, methods=["GET", "POST"]),
            Route("/health", health, methods=["GET"]),
        ],
        middleware=[Middleware(AuthMiddleware)],
    )


async def _call(app: Starlette, headers: dict[str, str] | None = None) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://t",
    ) as c:
        return await c.post("/mcp", headers=headers or {})


async def test_missing_authorization_header_returns_401():
    r = await _call(_make_app())
    assert r.status_code == 401
    body = r.json()
    assert body["error"] == "unauthorized"
    assert "API key" in body["message"]
    # No WWW-Authenticate header — we're API-key auth, not OAuth Bearer,
    # and MCP scanners read ``WWW-Authenticate: Bearer`` as an OAuth hint.
    assert "WWW-Authenticate" not in r.headers


async def test_empty_authorization_header_returns_401():
    r = await _call(_make_app(), headers={"Authorization": ""})
    assert r.status_code == 401


async def test_wrong_scheme_returns_401():
    # Basic auth instead of Bearer
    r = await _call(_make_app(), headers={"Authorization": "Basic Zm9vOmJhcg=="})
    assert r.status_code == 401


async def test_bearer_without_token_returns_401():
    r = await _call(_make_app(), headers={"Authorization": "Bearer"})
    assert r.status_code == 401


async def test_unknown_bearer_key_returns_401():
    r = await _call(
        _make_app(),
        headers={"Authorization": "Bearer gmcp_live_totally_not_a_real_key_please_ignore"},
    )
    assert r.status_code == 401


async def test_valid_key_reaches_handler():
    email = f"test-mw-{uuid.uuid4()}@example.test"
    raw, _ = await mint_key(email=email, label="middleware happy path")
    r = await _call(_make_app(), headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


async def test_revoked_key_returns_401():
    email = f"test-mw-{uuid.uuid4()}@example.test"
    raw, meta = await mint_key(email=email, label="middleware revoked path")
    ok = await revoke_key(meta["key_id"])
    assert ok is True
    r = await _call(_make_app(), headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 401


async def test_401_body_does_not_reveal_key_existence():
    # Missing header vs. header-with-unknown-key must return the same body
    # — otherwise an attacker could probe whether a specific key exists.
    r_missing = await _call(_make_app())
    r_unknown = await _call(
        _make_app(),
        headers={"Authorization": "Bearer gmcp_live_fake_probe"},
    )
    assert r_missing.status_code == 401
    assert r_unknown.status_code == 401
    assert r_missing.json() == r_unknown.json()


async def test_health_endpoint_bypasses_auth():
    # /health must be reachable without a Bearer header — it's used by
    # uptime monitors, load balancers, and the systemd healthcheck.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_make_app()),
        base_url="http://t",
    ) as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_health_endpoint_ignores_invalid_bearer():
    # A monitor might send a stale / bogus Authorization header by
    # accident. /health should still reply, not 401.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_make_app()),
        base_url="http://t",
    ) as c:
        r = await c.get("/health", headers={"Authorization": "Bearer bogus"})
    assert r.status_code == 200


async def test_case_insensitive_bearer_scheme():
    # RFC 7235 says the scheme match is case-insensitive. Our middleware
    # accepts lowercase / mixed-case 'bearer' (via .lower() in validate_header).
    email = f"test-mw-{uuid.uuid4()}@example.test"
    raw, _ = await mint_key(email=email, label="middleware case")
    r = await _call(_make_app(), headers={"Authorization": f"bearer {raw}"})
    assert r.status_code == 200


async def test_x_api_key_header_reaches_handler():
    # Some MCP hosting UIs (e.g. Smithery) can only forward a raw header
    # value with no scheme prefix. X-API-Key takes the raw key verbatim.
    email = f"test-mw-{uuid.uuid4()}@example.test"
    raw, _ = await mint_key(email=email, label="middleware x-api-key")
    r = await _call(_make_app(), headers={"X-API-Key": raw})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


async def test_unknown_x_api_key_returns_401():
    r = await _call(
        _make_app(),
        headers={"X-API-Key": "gmcp_live_totally_not_a_real_key_please_ignore"},
    )
    assert r.status_code == 401


async def test_revoked_x_api_key_returns_401():
    email = f"test-mw-{uuid.uuid4()}@example.test"
    raw, meta = await mint_key(email=email, label="middleware x-api-key revoked")
    ok = await revoke_key(meta["key_id"])
    assert ok is True
    r = await _call(_make_app(), headers={"X-API-Key": raw})
    assert r.status_code == 401


async def test_empty_x_api_key_header_returns_401():
    r = await _call(_make_app(), headers={"X-API-Key": ""})
    assert r.status_code == 401


async def test_x_api_key_with_surrounding_whitespace_still_validates():
    # Some config UIs wrap pasted values in whitespace. Tolerate it.
    email = f"test-mw-{uuid.uuid4()}@example.test"
    raw, _ = await mint_key(email=email, label="middleware x-api-key whitespace")
    r = await _call(_make_app(), headers={"X-API-Key": f"  {raw}  "})
    assert r.status_code == 200


async def test_bearer_wins_when_both_headers_present():
    # If a client sends both, a valid Authorization header should be
    # enough to authenticate — even if X-API-Key is nonsense.
    email = f"test-mw-{uuid.uuid4()}@example.test"
    raw, _ = await mint_key(email=email, label="middleware both headers")
    r = await _call(
        _make_app(),
        headers={"Authorization": f"Bearer {raw}", "X-API-Key": "garbage"},
    )
    assert r.status_code == 200


async def test_well_known_paths_bypass_auth():
    # MCP hosting scanners probe /.well-known/* for discovery metadata.
    # If auth returns 401 here, they assume the server requires OAuth
    # and never fall back to configSchema-based header auth. We don't
    # serve anything under /.well-known/, so we want a clean 404 — not a
    # 401 that changes the scanner's behaviour.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_make_app()),
        base_url="http://t",
    ) as c:
        r = await c.get("/.well-known/mcp/server-card.json")
    assert r.status_code == 404  # Starlette's default, not our 401


async def test_x_api_key_used_when_authorization_invalid():
    # If Authorization is present but malformed (wrong scheme, empty
    # token, ...), X-API-Key should still be accepted as a fallback.
    email = f"test-mw-{uuid.uuid4()}@example.test"
    raw, _ = await mint_key(email=email, label="middleware fallback")
    r = await _call(
        _make_app(),
        headers={"Authorization": "Basic notbearer", "X-API-Key": raw},
    )
    assert r.status_code == 200
