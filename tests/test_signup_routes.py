"""HTTP tests for /, /signup, /signup/verify.

Drives the FastMCP-built Starlette app through ``httpx.ASGITransport``
so every test shares the same asyncio event loop as the asyncpg pool.
"""
from __future__ import annotations

import uuid

import httpx
import pytest
from starlette.middleware import Middleware as ASGIMiddleware

from geo_mcp import signup as signup_mod
from geo_mcp.data_access.postgis import close_pool
from geo_mcp.middleware import AuthMiddleware
from geo_mcp.server import build_app

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _reset_pool():
    yield
    await close_pool()


@pytest.fixture
def stubbed_email(monkeypatch):
    captured: dict = {}

    async def _fake_send(email: str, raw_token: str) -> None:
        captured["email"] = email
        captured["token"] = raw_token

    monkeypatch.setattr(signup_mod, "_send_verification_email", _fake_send)
    return captured


def _client_for(app):
    http_app = app.http_app(middleware=[ASGIMiddleware(AuthMiddleware)])
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=http_app), base_url="http://t")


async def test_root_is_public():
    async with _client_for(build_app()) as c:
        r = await c.get("/")
    assert r.status_code == 200
    assert "geo-mcp" in r.text
    assert "Get a free API key" in r.text


async def test_signup_form_is_public():
    async with _client_for(build_app()) as c:
        r = await c.get("/signup")
    assert r.status_code == 200
    assert "<form" in r.text
    assert 'name="email"' in r.text


async def test_signup_post_stores_pending_and_shows_check_email(stubbed_email):
    email = f"route-{uuid.uuid4()}@example.test"
    async with _client_for(build_app()) as c:
        r = await c.post("/signup", data={"email": email})
    assert r.status_code == 200
    assert "Check your email" in r.text
    assert stubbed_email["email"] == email
    assert stubbed_email["token"]


async def test_signup_post_rejects_missing_email():
    async with _client_for(build_app()) as c:
        r = await c.post("/signup", data={})
    assert r.status_code == 400
    assert "valid email" in r.text.lower()


async def test_signup_post_silently_accepts_honeypot(stubbed_email):
    async with _client_for(build_app()) as c:
        r = await c.post("/signup", data={"email": "bot@example.test", "hp": "im-a-bot"})
    assert r.status_code == 200
    assert "Check your email" in r.text
    assert "email" not in stubbed_email


async def test_signup_verify_happy_path_shows_key(stubbed_email):
    email = f"route-{uuid.uuid4()}@example.test"
    async with _client_for(build_app()) as c:
        await c.post("/signup", data={"email": email})
        token = stubbed_email["token"]
        r = await c.get(f"/signup/verify?token={token}")
    assert r.status_code == 200
    assert "You're in" in r.text
    assert "gmcp_live_" in r.text


async def test_signup_verify_rejects_bad_token():
    async with _client_for(build_app()) as c:
        r = await c.get("/signup/verify?token=garbage")
    assert r.status_code == 400
    assert "invalid or has expired" in r.text


async def test_signup_verify_rejects_missing_token():
    async with _client_for(build_app()) as c:
        r = await c.get("/signup/verify")
    assert r.status_code == 400


async def test_client_ip_prefers_cf_connecting_ip():
    # Direct unit test of _client_ip header precedence.
    from starlette.requests import Request
    from geo_mcp.server import _client_ip

    scope = {
        "type": "http",
        "headers": [
            (b"cf-connecting-ip", b"203.0.113.9"),
            (b"x-forwarded-for", b"1.2.3.4, 5.6.7.8"),
        ],
        "client": ("10.0.0.1", 52345),
    }
    req = Request(scope)
    assert _client_ip(req) == "203.0.113.9"


async def test_client_ip_xff_takes_last_entry_not_first():
    # Without CF, fallback to X-Forwarded-For's LAST value
    # (the nearest hop, hardest to spoof — not the first which is
    # client-supplied).
    from starlette.requests import Request
    from geo_mcp.server import _client_ip

    scope = {
        "type": "http",
        "headers": [(b"x-forwarded-for", b"1.2.3.4, 203.0.113.9")],
        "client": ("10.0.0.1", 52345),
    }
    req = Request(scope)
    assert _client_ip(req) == "203.0.113.9"


async def test_client_ip_falls_back_to_socket_peer():
    from starlette.requests import Request
    from geo_mcp.server import _client_ip

    scope = {
        "type": "http",
        "headers": [],
        "client": ("10.0.0.1", 52345),
    }
    req = Request(scope)
    assert _client_ip(req) == "10.0.0.1"
