"""OAuth 2.1 tests — full happy path and each negative-auth branch.

We drive the Starlette routes via httpx.ASGITransport against the real
build_app() so the tests exercise the actual HTTP contract (form parsing,
redirects, status codes, headers) — not just the business-logic helpers.

Test fixtures mint real rows in meta.api_keys / meta.oauth_clients /
meta.oauth_auth_codes; conftest.py cleans up all ``%@example.test``
customers + their related rows at session end.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from geo_mcp.auth import mint_key
from geo_mcp.oauth import register_client
from geo_mcp.server import build_app

pytestmark = pytest.mark.asyncio


def _pkce_pair() -> tuple[str, str]:
    """Generate (verifier, S256 challenge)."""
    verifier = secrets.token_urlsafe(48)[:64]  # 64 chars
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


async def _client():
    # FastMCP's build_app returns a FastMCP instance. The underlying ASGI
    # app is what we want for httpx.ASGITransport.
    app = build_app()
    # Construct the HTTP ASGI application.
    asgi = app.http_app()
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=asgi),
        base_url="http://t",
        follow_redirects=False,
    )


# ---------------------------------------------------------------------------
# Discovery endpoints
# ---------------------------------------------------------------------------


async def test_protected_resource_metadata_shape():
    async with await _client() as c:
        r = await c.get("/.well-known/oauth-protected-resource")
    assert r.status_code == 200
    body = r.json()
    assert "resource" in body
    assert "authorization_servers" in body
    assert body["bearer_methods_supported"] == ["header"]


async def test_protected_resource_metadata_mcp_variant():
    async with await _client() as c:
        r = await c.get("/.well-known/oauth-protected-resource/mcp")
    assert r.status_code == 200
    # Same document as the non-mcp variant — clients probe both.
    assert "authorization_servers" in r.json()


async def test_authorization_server_metadata_shape():
    async with await _client() as c:
        r = await c.get("/.well-known/oauth-authorization-server")
    assert r.status_code == 200
    body = r.json()
    assert body["grant_types_supported"] == ["authorization_code"]
    assert body["response_types_supported"] == ["code"]
    assert body["code_challenge_methods_supported"] == ["S256"]
    assert body["token_endpoint_auth_methods_supported"] == ["none"]
    for key in ("authorization_endpoint", "token_endpoint", "registration_endpoint"):
        assert body[key].endswith(key.replace("_endpoint", "").replace("_", "/"))  \
            or body[key].endswith("/oauth/authorize") \
            or body[key].endswith("/oauth/token") \
            or body[key].endswith("/oauth/register")


# ---------------------------------------------------------------------------
# Dynamic client registration
# ---------------------------------------------------------------------------


async def test_register_client_happy_path():
    async with await _client() as c:
        r = await c.post("/oauth/register", json={
            "client_name": "test-oauth-happy",
            "redirect_uris": ["https://example.test/callback"],
        })
    assert r.status_code == 201
    body = r.json()
    assert body["client_name"] == "test-oauth-happy"
    assert body["redirect_uris"] == ["https://example.test/callback"]
    assert len(body["client_id"]) >= 20
    assert body["token_endpoint_auth_method"] == "none"


async def test_register_client_rejects_missing_redirect_uris():
    async with await _client() as c:
        r = await c.post("/oauth/register", json={"client_name": "test-oauth-missing"})
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_client_metadata"


async def test_register_client_rejects_javascript_scheme():
    # Open-redirect sanity — we don't let clients register a URI scheme
    # that would execute script in the browser on redirect.
    async with await _client() as c:
        r = await c.post("/oauth/register", json={
            "client_name": "test-oauth-xss",
            "redirect_uris": ["javascript:alert(1)"],
        })
    assert r.status_code == 400


async def test_register_client_rejects_too_many_redirect_uris():
    async with await _client() as c:
        r = await c.post("/oauth/register", json={
            "client_name": "test-oauth-flood",
            "redirect_uris": [f"https://example.test/{i}" for i in range(50)],
        })
    assert r.status_code == 400


async def test_register_client_rejects_non_json_body():
    async with await _client() as c:
        r = await c.post("/oauth/register", content="not-json",
                         headers={"Content-Type": "application/json"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Authorization endpoint (GET renders consent, POST issues code)
# ---------------------------------------------------------------------------


async def test_authorize_get_rejects_unknown_client():
    async with await _client() as c:
        r = await c.get("/oauth/authorize", params={
            "response_type": "code",
            "client_id": "nope",
            "redirect_uri": "https://example.test/cb",
            "code_challenge": "x" * 43,
            "code_challenge_method": "S256",
        })
    assert r.status_code == 400


async def test_authorize_get_rejects_plain_pkce():
    reg = await register_client({
        "client_name": "test-oauth-plain-pkce",
        "redirect_uris": ["https://example.test/cb"],
    })
    async with await _client() as c:
        r = await c.get("/oauth/authorize", params={
            "response_type": "code",
            "client_id": reg.client_id,
            "redirect_uri": "https://example.test/cb",
            "code_challenge": "x" * 43,
            "code_challenge_method": "plain",
        })
    assert r.status_code == 400


async def test_authorize_get_rejects_untrusted_redirect_uri():
    reg = await register_client({
        "client_name": "test-oauth-redirect",
        "redirect_uris": ["https://example.test/cb"],
    })
    async with await _client() as c:
        r = await c.get("/oauth/authorize", params={
            "response_type": "code",
            "client_id": reg.client_id,
            "redirect_uri": "https://attacker.test/steal",
            "code_challenge": "x" * 43,
            "code_challenge_method": "S256",
        })
    assert r.status_code == 400


async def test_authorize_get_renders_consent_form():
    reg = await register_client({
        "client_name": "test-oauth-consent",
        "redirect_uris": ["https://example.test/cb"],
    })
    async with await _client() as c:
        r = await c.get("/oauth/authorize", params={
            "response_type": "code",
            "client_id": reg.client_id,
            "redirect_uri": "https://example.test/cb",
            "code_challenge": "x" * 43,
            "code_challenge_method": "S256",
            "state": "xyz",
        })
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "api_key" in r.text
    assert "test-oauth-consent" in r.text


async def test_authorize_post_redirects_with_code_on_valid_key():
    reg = await register_client({
        "client_name": "test-oauth-authpost",
        "redirect_uris": ["https://example.test/cb"],
    })
    email = f"test-oauth-{uuid.uuid4()}@example.test"
    raw_key, _ = await mint_key(email=email, label="oauth test user")
    _, challenge = _pkce_pair()
    async with await _client() as c:
        r = await c.post("/oauth/authorize", data={
            "response_type": "code",
            "client_id": reg.client_id,
            "redirect_uri": "https://example.test/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "preserve-me",
            "api_key": raw_key,
        })
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("https://example.test/cb?")
    q = parse_qs(urlparse(loc).query)
    assert "code" in q
    assert q["state"] == ["preserve-me"]


async def test_authorize_post_rerenders_on_bad_key():
    reg = await register_client({
        "client_name": "test-oauth-badkey",
        "redirect_uris": ["https://example.test/cb"],
    })
    _, challenge = _pkce_pair()
    async with await _client() as c:
        r = await c.post("/oauth/authorize", data={
            "response_type": "code",
            "client_id": reg.client_id,
            "redirect_uri": "https://example.test/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "api_key": "gmcp_live_not_a_real_key",
        })
    # 400 with the consent form re-rendered (error visible on page).
    assert r.status_code == 400
    assert "api_key" in r.text


async def test_authorize_post_missing_key_rerenders():
    reg = await register_client({
        "client_name": "test-oauth-nokey",
        "redirect_uris": ["https://example.test/cb"],
    })
    _, challenge = _pkce_pair()
    async with await _client() as c:
        r = await c.post("/oauth/authorize", data={
            "response_type": "code",
            "client_id": reg.client_id,
            "redirect_uri": "https://example.test/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Token endpoint — happy path + every negative branch
# ---------------------------------------------------------------------------


async def _get_code(c: httpx.AsyncClient, reg_name: str, redirect_uri: str):
    """Helper: register client → authorize → pull code + verifier back."""
    reg = await register_client({
        "client_name": reg_name,
        "redirect_uris": [redirect_uri],
    })
    email = f"test-oauth-{uuid.uuid4()}@example.test"
    raw_key, _ = await mint_key(email=email, label="oauth test flow")
    verifier, challenge = _pkce_pair()
    r = await c.post("/oauth/authorize", data={
        "response_type": "code",
        "client_id": reg.client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "api_key": raw_key,
    })
    assert r.status_code == 302
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    return reg, verifier, code


async def test_token_happy_path_returns_bearer_token():
    async with await _client() as c:
        reg, verifier, code = await _get_code(c, "test-oauth-happy-token",
                                              "https://example.test/cb")
        r = await c.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://example.test/cb",
            "client_id": reg.client_id,
            "code_verifier": verifier,
        })
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "Bearer"
    assert body["access_token"].startswith("gmcp_live_")
    # No-store ensures intermediaries don't cache the token.
    assert r.headers["cache-control"] == "no-store"


async def test_token_rejects_wrong_grant_type():
    async with await _client() as c:
        reg, verifier, code = await _get_code(c, "test-oauth-wrong-grant",
                                              "https://example.test/cb")
        r = await c.post("/oauth/token", data={
            "grant_type": "password",
            "code": code,
            "redirect_uri": "https://example.test/cb",
            "client_id": reg.client_id,
            "code_verifier": verifier,
        })
    assert r.status_code == 400
    assert r.json()["error"] == "unsupported_grant_type"


async def test_token_rejects_reused_code():
    """One-shot codes — a successful exchange burns the code."""
    async with await _client() as c:
        reg, verifier, code = await _get_code(c, "test-oauth-reuse",
                                              "https://example.test/cb")
        r1 = await c.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://example.test/cb",
            "client_id": reg.client_id,
            "code_verifier": verifier,
        })
        assert r1.status_code == 200
        # Replay — same code, should fail.
        r2 = await c.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://example.test/cb",
            "client_id": reg.client_id,
            "code_verifier": verifier,
        })
    assert r2.status_code == 400
    assert r2.json()["error"] == "invalid_grant"


async def test_token_rejects_wrong_pkce_verifier():
    async with await _client() as c:
        reg, _verifier, code = await _get_code(c, "test-oauth-wrong-pkce",
                                               "https://example.test/cb")
        bad_verifier = secrets.token_urlsafe(48)[:64]
        r = await c.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://example.test/cb",
            "client_id": reg.client_id,
            "code_verifier": bad_verifier,
        })
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"


async def test_token_rejects_redirect_uri_mismatch():
    async with await _client() as c:
        reg, verifier, code = await _get_code(c, "test-oauth-redir-mismatch",
                                              "https://example.test/cb")
        r = await c.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://example.test/different",
            "client_id": reg.client_id,
            "code_verifier": verifier,
        })
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"


async def test_token_rejects_wrong_client_id():
    async with await _client() as c:
        reg, verifier, code = await _get_code(c, "test-oauth-client-mismatch",
                                              "https://example.test/cb")
        # Register a separate client, send their id on the exchange.
        other = await register_client({
            "client_name": "test-oauth-attacker",
            "redirect_uris": ["https://example.test/cb"],
        })
        r = await c.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://example.test/cb",
            "client_id": other.client_id,
            "code_verifier": verifier,
        })
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"


async def test_token_rejects_missing_pkce_verifier():
    async with await _client() as c:
        reg, _verifier, code = await _get_code(c, "test-oauth-no-verifier",
                                               "https://example.test/cb")
        r = await c.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://example.test/cb",
            "client_id": reg.client_id,
        })
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_request"


async def test_token_minted_key_validates_as_bearer():
    """The OAuth-minted access_token should work as a normal API key
    against our middleware — proving the access-tokens-are-api-keys
    design actually closes the loop."""
    from geo_mcp.auth import validate_header
    async with await _client() as c:
        reg, verifier, code = await _get_code(c, "test-oauth-roundtrip",
                                              "https://example.test/cb")
        r = await c.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://example.test/cb",
            "client_id": reg.client_id,
            "code_verifier": verifier,
        })
    assert r.status_code == 200
    raw = r.json()["access_token"]
    ctx = await validate_header(f"Bearer {raw}", None)
    assert ctx is not None
    assert ctx.tier == "free"
