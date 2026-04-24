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
    """Build a test client that talks to the real ASGI app.

    GEO_MCP_PUBLIC_BASE_URL matches the httpx base_url so the CSRF
    Origin check on POST /oauth/authorize accepts requests from this
    fake origin. Real browsers always attach Origin; httpx does not,
    so we also set a headers default on the client itself below."""
    import os as _os
    _os.environ["GEO_MCP_PUBLIC_BASE_URL"] = "http://t"
    app = build_app()
    asgi = app.http_app()
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=asgi),
        base_url="http://t",
        follow_redirects=False,
        headers={"Origin": "http://t"},
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


async def test_register_client_rejects_cleartext_http_non_loopback():
    async with await _client() as c:
        r = await c.post("/oauth/register", json={
            "client_name": "test-oauth-cleartext",
            "redirect_uris": ["http://attacker.test/cb"],
        })
    assert r.status_code == 400


async def test_register_client_rejects_userinfo_in_uri():
    # https://user:pass@host — an opaque credential-smuggling vector.
    async with await _client() as c:
        r = await c.post("/oauth/register", json={
            "client_name": "test-oauth-userinfo",
            "redirect_uris": ["https://user:pass@example.test/cb"],
        })
    assert r.status_code == 400


async def test_register_client_accepts_http_localhost():
    # Native + CLI dev flows (Claude Desktop's loopback callback, etc.)
    # legitimately use http://localhost. Must stay allowed.
    async with await _client() as c:
        r = await c.post("/oauth/register", json={
            "client_name": "test-oauth-localhost",
            "redirect_uris": ["http://localhost:8765/cb"],
        })
    assert r.status_code == 201


async def test_register_client_rejects_control_chars_in_name():
    async with await _client() as c:
        r = await c.post("/oauth/register", json={
            "client_name": "test-oauth-\x1b[31mBAD",
            "redirect_uris": ["https://example.test/cb"],
        })
    assert r.status_code == 400


async def test_token_exchange_cap_stops_oauth_key_farming():
    """Per-customer cap on oauth:* keys — C2 in the security review."""
    from geo_mcp import oauth as oauth_mod
    # Make the cap easily hit in a test without really minting 20 keys.
    # monkeypatch doesn't play with module-level consts cleanly; replace
    # the attribute and restore below.
    original = oauth_mod._MAX_OAUTH_KEYS_PER_CUSTOMER
    oauth_mod._MAX_OAUTH_KEYS_PER_CUSTOMER = 2
    try:
        async with await _client() as c:
            # Same email across all flows → same customer.
            email = f"test-oauth-cap-{uuid.uuid4()}@example.test"
            granter, _ = await mint_key(email=email, label="cap test granter")
            reg = await register_client({
                "client_name": "test-oauth-cap",
                "redirect_uris": ["https://example.test/cb"],
            })

            async def _mint_via_oauth() -> int:
                verifier, challenge = _pkce_pair()
                r = await c.post("/oauth/authorize", data={
                    "response_type": "code",
                    "client_id": reg.client_id,
                    "redirect_uri": "https://example.test/cb",
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "api_key": granter,
                })
                if r.status_code != 302:
                    return r.status_code
                code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
                tr = await c.post("/oauth/token", data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": "https://example.test/cb",
                    "client_id": reg.client_id,
                    "code_verifier": verifier,
                })
                return tr.status_code

            # First two succeed (cap = 2 total oauth keys; plus the
            # granter which is NOT labelled oauth:*, so doesn't count).
            assert await _mint_via_oauth() == 200
            assert await _mint_via_oauth() == 200
            # Third hits the cap.
            assert await _mint_via_oauth() == 400
    finally:
        oauth_mod._MAX_OAUTH_KEYS_PER_CUSTOMER = original


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


async def test_authorize_post_blocks_cross_origin():
    """CSRF defence — POST from a foreign origin must be rejected even
    if all other parameters and the API key are valid. This is the
    single most important security property of the consent endpoint."""
    reg = await register_client({
        "client_name": "test-oauth-csrf",
        "redirect_uris": ["https://example.test/cb"],
    })
    email = f"test-oauth-{uuid.uuid4()}@example.test"
    raw_key, _ = await mint_key(email=email, label="oauth test csrf")
    _, challenge = _pkce_pair()
    async with await _client() as c:
        r = await c.post("/oauth/authorize",
                         headers={"Origin": "https://attacker.test"},
                         data={
            "response_type": "code",
            "client_id": reg.client_id,
            "redirect_uri": "https://example.test/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "api_key": raw_key,
        })
    assert r.status_code == 403


async def test_authorize_post_blocks_missing_origin():
    """No Origin AND no Referer → block. Legit browsers always send at
    least one of these on form POSTs."""
    reg = await register_client({
        "client_name": "test-oauth-noorigin",
        "redirect_uris": ["https://example.test/cb"],
    })
    _, challenge = _pkce_pair()
    # Strip the default Origin header by overriding with an empty one.
    async with await _client() as c:
        r = await c.post("/oauth/authorize",
                         headers={"Origin": "", "Referer": ""},
                         data={
            "response_type": "code",
            "client_id": reg.client_id,
            "redirect_uri": "https://example.test/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "api_key": "ignored",
        })
    assert r.status_code == 403


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


async def test_token_response_omits_expires_in():
    """We deliberately don't send expires_in — access tokens are
    long-lived API keys; advertising a TTL misleads well-behaved
    clients into a pointless re-auth dance."""
    async with await _client() as c:
        reg, verifier, code = await _get_code(c, "test-oauth-noexpiry",
                                              "https://example.test/cb")
        r = await c.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://example.test/cb",
            "client_id": reg.client_id,
            "code_verifier": verifier,
        })
    assert r.status_code == 200
    assert "expires_in" not in r.json()


async def test_revoke_endpoint_revokes_token():
    from geo_mcp.auth import validate_header
    async with await _client() as c:
        reg, verifier, code = await _get_code(c, "test-oauth-revoke",
                                              "https://example.test/cb")
        tr = await c.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://example.test/cb",
            "client_id": reg.client_id,
            "code_verifier": verifier,
        })
        assert tr.status_code == 200
        token = tr.json()["access_token"]

        # Pre-revoke: validates.
        assert await validate_header(f"Bearer {token}", None) is not None

        rv = await c.post("/oauth/revoke", data={"token": token})
        assert rv.status_code == 200
        # RFC 7009 §2.2 — unknown/revoked tokens still return 200 so
        # attackers can't probe token existence.
        assert rv.headers.get("cache-control") == "no-store"

        # Post-revoke: no longer validates.
        assert await validate_header(f"Bearer {token}", None) is None


async def test_revoke_unknown_token_still_200():
    """RFC 7009 §2.2 — the endpoint must return 200 for unknown tokens
    so attackers can't use response codes to probe which tokens exist."""
    async with await _client() as c:
        r = await c.post("/oauth/revoke", data={"token": "gmcp_live_never_existed"})
    assert r.status_code == 200


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
