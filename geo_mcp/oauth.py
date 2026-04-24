"""OAuth 2.1 authorization-code + PKCE flow for MCP hosting platforms.

Why this exists alongside static API keys:

Direct clients (Claude Desktop, Cursor, curl) authenticate with a
static ``Authorization: Bearer <key>`` or ``X-API-Key: <key>`` header
and never touch the OAuth endpoints. They work because API-key headers
are the fastest possible auth and the user already has a key.

Hosting platforms (Smithery, and any future directory that enforces
the MCP authorization spec) can't use static keys cleanly — their
catalogue validators expect OAuth 2.1 discovery endpoints and a full
authorization-code handshake. Without them the publish flow falls
into a loop waiting for OAuth discovery to succeed. So we layer a
minimum-viable OAuth 2.1 authorization server on top of the existing
API-key machinery.

Implementation notes:

* **Dynamic client registration (RFC 7591).** Open — any client can
  register. The MCP spec's threat model treats hosting platforms as
  public clients; PKCE S256 protects the authorization code.
* **PKCE S256 required** — we reject the deprecated ``plain`` method.
* **Access tokens ARE API keys.** /oauth/token mints a new
  ``meta.api_keys`` row labelled ``oauth:<client_name>`` and returns
  its plaintext as ``access_token``. Downstream, the existing middleware
  validates these tokens exactly like a hand-minted key: rate-limiting,
  usage-logging, and revocation all "just work". The user can revoke
  the hosting platform's access any time by revoking that one key,
  without touching their personal key.
* **No refresh tokens.** Access tokens are long-lived by design (they
  are API keys; the user controls revocation).
* **User auth at the authorization endpoint** is API-key-by-paste:
  the consent page asks the user to paste their geo-mcp key. That key
  is *not* the one Smithery will use — it's the proof that the user
  controls the account. A fresh key is minted for the platform.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import logging
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from geo_mcp.auth import lookup_raw_key, mint_key
from geo_mcp.data_access.postgis import get_pool

log = logging.getLogger(__name__)

AUTH_CODE_TTL = timedelta(minutes=10)
_CODE_BYTES = 32           # → 43 url-safe base64 chars
_CLIENT_ID_BYTES = 24      # → 32 url-safe base64 chars
_MAX_REDIRECT_URIS = 10    # cap per client to prevent registration abuse

# Cap active (non-revoked) oauth-minted keys per customer. Prevents a
# single compromised API key from being spun into an arbitrary number
# of durable child keys before the user notices the breach.
_MAX_OAUTH_KEYS_PER_CUSTOMER = 20

# Only A–Z a–z 0–9 plus a small punctuation set — rejects control chars
# (which could mangle log output when embedded in ``oauth:<name>``
# labels) and dedicated separators (commas, pipes). Matches RFC 7591
# guidance that display names be printable text.
_CLIENT_NAME_RE = re.compile(r"^[A-Za-z0-9 _./+()\-]{1,64}$")


# ---------------------------------------------------------------------------
# Discovery metadata
# ---------------------------------------------------------------------------


def public_base_url() -> str:
    """Canonical external URL — the issuer in OAuth metadata + prefix for
    all discovery / endpoint URLs. Falls back to localhost in dev."""
    return os.getenv("GEO_MCP_PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def oauth_protected_resource_metadata() -> dict[str, Any]:
    """RFC 9728 — protected-resource metadata. Tells clients which
    authorization server they need to talk to in order to get tokens
    for this resource server. We're both AS and RS, so ``authorization_servers``
    lists ourselves."""
    base = public_base_url()
    return {
        "resource": base,
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
        "resource_documentation": f"{base}/privacy",
    }


def oauth_authorization_server_metadata() -> dict[str, Any]:
    """RFC 8414 — authorization-server metadata. Describes the endpoints
    and protocol flavours we support. Deliberately minimal: one flow
    (authorization_code + PKCE-S256), public clients only, no refresh."""
    base = public_base_url()
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "revocation_endpoint": f"{base}/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        # Public clients — no client_secret — PKCE carries the security.
        "token_endpoint_auth_methods_supported": ["none"],
        "revocation_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp"],
    }


# ---------------------------------------------------------------------------
# Dynamic client registration (RFC 7591)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClientRegistration:
    client_id: str
    client_name: str | None
    redirect_uris: list[str]
    created_at: datetime


def _validate_redirect_uri(uri: str) -> bool:
    """Strict whitelist per RFC 8252:

      * ``https://`` — production web apps.
      * ``http://localhost`` / ``http://127.0.0.1`` (+ port) — native +
        CLI dev flows that spin up a transient loopback listener.
      * Non-``http(s)`` custom schemes (e.g. ``myapp://`` for mobile).

    Rejects: ``http://anything-else`` (cleartext traffic to non-loopback
    hosts), ``userinfo@`` (opaque cred smuggling), and script-capable
    schemes (``javascript:``, ``data:``, ``vbscript:``, ``file:``,
    ``about:``). Length-capped at 2kB — any longer is abuse, not
    legitimate OAuth.
    """
    if not uri or len(uri) > 2048:
        return False
    try:
        u = urlparse(uri.strip())
    except ValueError:
        return False
    if not u.scheme or not u.netloc and u.scheme in ("http", "https"):
        return False
    if u.username or u.password:
        return False
    banned_schemes = {"javascript", "data", "file", "vbscript", "about"}
    if u.scheme.lower() in banned_schemes:
        return False
    if u.scheme.lower() == "http":
        host = (u.hostname or "").lower()
        if host not in ("localhost", "127.0.0.1", "::1"):
            return False
    return True


async def register_client(metadata: dict[str, Any]) -> ClientRegistration:
    """RFC 7591 — create a new OAuth client. Accepts minimal metadata:
    ``redirect_uris`` (required) and ``client_name`` (optional). We
    ignore other fields (scope, grant_types, etc.) — our only supported
    flow is authorization_code with PKCE, so there's nothing to negotiate."""
    redirect_uris = metadata.get("redirect_uris") or []
    if not isinstance(redirect_uris, list) or not redirect_uris:
        raise ValueError("redirect_uris required")
    if len(redirect_uris) > _MAX_REDIRECT_URIS:
        raise ValueError(f"at most {_MAX_REDIRECT_URIS} redirect_uris allowed")
    for uri in redirect_uris:
        if not isinstance(uri, str) or not _validate_redirect_uri(uri):
            raise ValueError(f"invalid redirect_uri: {uri!r}")

    client_name = metadata.get("client_name")
    if client_name is not None:
        if not isinstance(client_name, str) or not _CLIENT_NAME_RE.fullmatch(client_name):
            raise ValueError(
                "invalid client_name (1–64 chars, letters/digits/"
                "spaces/._+()/ - only)"
            )

    client_id = secrets.token_urlsafe(_CLIENT_ID_BYTES)

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO meta.oauth_clients (id, name, redirect_uris)
            VALUES ($1, $2, $3)
            RETURNING id, name, redirect_uris, created_at
            """,
            client_id, client_name, redirect_uris,
        )
    return ClientRegistration(
        client_id=row["id"],
        client_name=row["name"],
        redirect_uris=list(row["redirect_uris"]),
        created_at=row["created_at"],
    )


async def get_client(client_id: str) -> ClientRegistration | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, redirect_uris, created_at FROM meta.oauth_clients WHERE id = $1",
            client_id,
        )
    if row is None:
        return None
    return ClientRegistration(
        client_id=row["id"],
        client_name=row["name"],
        redirect_uris=list(row["redirect_uris"]),
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# Authorization code issuance (GET/POST /oauth/authorize)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthorizeParams:
    """Parsed + validated query parameters from GET /oauth/authorize.
    If any field is None, the caller must render an error instead of
    redirecting (to avoid open-redirect via an unvalidated redirect_uri).
    """
    client: ClientRegistration
    redirect_uri: str
    state: str | None
    code_challenge: str
    code_challenge_method: str
    scope: str | None


async def validate_authorize_request(
    client_id: str | None,
    redirect_uri: str | None,
    response_type: str | None,
    code_challenge: str | None,
    code_challenge_method: str | None,
    state: str | None = None,
    scope: str | None = None,
) -> tuple[AuthorizeParams | None, str]:
    """Pre-flight validation for the authorization endpoint.

    Returns ``(params, "")`` on success, ``(None, error_message)`` on
    failure. The caller uses the error message for an HTML error page
    when redirect_uri isn't trusted; otherwise it redirects back to the
    client with an OAuth ``error`` query parameter.
    """
    if response_type != "code":
        return None, "unsupported_response_type: only 'code' is supported"
    if not client_id:
        return None, "missing client_id"
    if not redirect_uri:
        return None, "missing redirect_uri"
    if not code_challenge:
        return None, "missing code_challenge (PKCE required)"
    if code_challenge_method != "S256":
        return None, "code_challenge_method must be 'S256'"
    # Per RFC 7636, the code_verifier is 43-128 chars of url-safe base64,
    # so the S256 challenge is exactly 43 chars. Enforce that shape
    # defensively so a malformed challenge can't slip through.
    if len(code_challenge) < 43 or len(code_challenge) > 128:
        return None, "invalid code_challenge length"

    client = await get_client(client_id)
    if client is None:
        return None, "unknown client_id"
    if redirect_uri not in client.redirect_uris:
        return None, "redirect_uri not registered for this client"

    return AuthorizeParams(
        client=client,
        redirect_uri=redirect_uri,
        state=state,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        scope=scope,
    ), ""


async def issue_authorization_code(
    params: AuthorizeParams,
    user_api_key: str,
) -> tuple[str, str] | tuple[None, str]:
    """User has pasted their API key to consent. If the key is valid,
    mint a one-time authorization code bound to that user's account +
    the PKCE challenge. Returns ``(code, "")`` on success or
    ``(None, reason)`` on failure (reason is a short string suitable for
    re-rendering the consent form)."""
    ctx = await lookup_raw_key(user_api_key.strip())
    if ctx is None:
        return None, "Invalid or revoked API key."

    code = secrets.token_urlsafe(_CODE_BYTES)
    expires_at = datetime.now(timezone.utc) + AUTH_CODE_TTL

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO meta.oauth_auth_codes
                (code, client_id, granter_api_key_id, customer_id,
                 code_challenge, code_challenge_method,
                 redirect_uri, scope, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            code, params.client.client_id, ctx.api_key_id, ctx.customer_id,
            params.code_challenge, params.code_challenge_method,
            params.redirect_uri, params.scope, expires_at,
        )
    log.info(
        "oauth authorize: client=%s customer=%s",
        params.client.client_id, ctx.customer_id,
    )
    return code, ""


# ---------------------------------------------------------------------------
# Token exchange (POST /oauth/token)
# ---------------------------------------------------------------------------


def _pkce_verify(code_verifier: str, code_challenge: str) -> bool:
    """S256: BASE64URL-NOPAD(SHA256(code_verifier)) == code_challenge."""
    import base64
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    # Constant-time to neutralise timing oracles on the challenge.
    return hmac.compare_digest(expected, code_challenge)


async def exchange_code_for_token(
    grant_type: str | None,
    code: str | None,
    redirect_uri: str | None,
    client_id: str | None,
    code_verifier: str | None,
) -> dict[str, Any]:
    """RFC 6749 §4.1.3 + RFC 7636.

    Atomic single-use: we DELETE the code row ... RETURNING under
    a transaction so two concurrent exchange attempts can't both succeed.
    On validation failure we raise ``ValueError`` and the Starlette route
    maps it to a 400 response with a JSON ``error`` body.
    """
    if grant_type != "authorization_code":
        raise ValueError(f"unsupported_grant_type: {grant_type!r}")
    if not code:
        raise ValueError("invalid_request: missing code")
    if not redirect_uri:
        raise ValueError("invalid_request: missing redirect_uri")
    if not client_id:
        raise ValueError("invalid_request: missing client_id")
    if not code_verifier:
        raise ValueError("invalid_request: missing code_verifier (PKCE required)")
    # RFC 7636 §4.1: verifier must be 43–128 chars.
    if len(code_verifier) < 43 or len(code_verifier) > 128:
        raise ValueError("invalid_grant: malformed code_verifier")

    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        # Validate first, THEN consume the code. If we deleted on any
        # validation failure (client_id / redirect_uri / PKCE mismatch),
        # a legit client losing a race against an attacker with a leaked
        # code would see ``invalid_grant`` on their own exchange —
        # effectively a DoS oracle. SELECT ... FOR UPDATE serialises
        # concurrent redeem attempts so exactly one wins the subsequent
        # DELETE; the loser gets a 0-row DELETE and raises below.
        row = await conn.fetchrow(
            """
            SELECT client_id, granter_api_key_id, customer_id,
                   code_challenge, code_challenge_method,
                   redirect_uri, scope
              FROM meta.oauth_auth_codes
             WHERE code = $1
               AND expires_at > now()
               AND used_at IS NULL
             FOR UPDATE
            """,
            code,
        )
        if row is None:
            raise ValueError("invalid_grant: code unknown, expired, or already used")
        # All post-lookup error descriptions collapse to a single opaque
        # string so the client can't distinguish which bound parameter
        # was wrong — closes the mismatch oracle.
        if not hmac.compare_digest(row["client_id"], client_id):
            raise ValueError("invalid_grant: authorization grant is invalid")
        if not hmac.compare_digest(row["redirect_uri"], redirect_uri):
            raise ValueError("invalid_grant: authorization grant is invalid")
        if not _pkce_verify(code_verifier, row["code_challenge"]):
            raise ValueError("invalid_grant: authorization grant is invalid")

        # All checks passed — burn the code now. This is inside the
        # same transaction so concurrent redeems serialise on the row
        # lock and only one proceeds.
        deleted = await conn.execute(
            "DELETE FROM meta.oauth_auth_codes WHERE code = $1",
            code,
        )
        if not deleted.endswith(" 1"):
            raise ValueError("invalid_grant: authorization grant is invalid")

        customer_id = row["customer_id"]
        # Look up the customer's email so mint_key can reuse the existing
        # row rather than the anonymous insert path.
        email_row = await conn.fetchrow(
            "SELECT email FROM meta.customers WHERE id = $1",
            customer_id,
        )
        if email_row is None:
            raise ValueError("server_error: customer not found")
        email = email_row["email"]

        # Per-customer cap on oauth-minted keys — a stolen granter key
        # can't be spun into an arbitrary number of durable children.
        active_count = await conn.fetchval(
            """
            SELECT count(*) FROM meta.api_keys
             WHERE customer_id = $1
               AND revoked_at IS NULL
               AND label LIKE 'oauth:%'
            """,
            customer_id,
        )
        if active_count >= _MAX_OAUTH_KEYS_PER_CUSTOMER:
            raise ValueError(
                "invalid_grant: oauth key cap reached for this account "
                "(revoke unused keys before reconnecting)"
            )

    client = await get_client(client_id)
    label = f"oauth:{client.client_name}" if client and client.client_name else "oauth"
    raw_token, _meta = await mint_key(email=email, label=label)
    log.info(
        "oauth token issued: client=%s customer=%s label=%s",
        client_id, customer_id, label,
    )
    return {
        "access_token": raw_token,
        "token_type": "Bearer",
        # No ``expires_in`` — access tokens are long-lived API keys
        # whose lifecycle is managed by revocation, not a TTL. Per
        # RFC 6749 §5.1 the field is optional; omitting it signals
        # "not short-lived" and stops well-behaved clients from
        # silently re-running the auth dance (and accumulating orphan
        # oauth:* rows on meta.api_keys) after an arbitrary cutoff.
        "scope": row["scope"] or "mcp",
    }


# ---------------------------------------------------------------------------
# Token revocation (RFC 7009)
# ---------------------------------------------------------------------------


async def revoke_token(token: str) -> None:
    """Revoke an access token. Idempotent per RFC 7009: we never signal
    back whether the token was known — unknown tokens return silently.

    Implementation note: we store access tokens as rows in
    ``meta.api_keys``, so revocation is literally ``revoke_key`` on the
    row matching the submitted token hash. Caller (HTTP handler) should
    respond 200 with no body regardless of the lookup outcome."""
    from geo_mcp.auth import hash_key, legacy_hash_key
    if not token:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Try canonical + legacy hashes so a pre-pepper token still
        # revokes cleanly. No-op if neither matches (RFC 7009 §2.2).
        await conn.execute(
            """
            UPDATE meta.api_keys
               SET revoked_at = now()
             WHERE key_hash = ANY($1::text[])
               AND revoked_at IS NULL
            """,
            [hash_key(token), legacy_hash_key(token)],
        )


# ---------------------------------------------------------------------------
# Authorization-page HTML
# ---------------------------------------------------------------------------


def authorize_page_html(
    params: AuthorizeParams,
    error: str | None = None,
) -> str:
    """Render the consent form: "Client X wants access — paste your key."
    Imports the _shell helper lazily to avoid a circular import with server.py."""
    from geo_mcp.server import _shell

    client_name = params.client.client_name or params.client.client_id[:12]
    redirect_host = urlparse(params.redirect_uri).netloc or params.redirect_uri
    # Hidden form fields — we round-trip the authorization request params
    # through the form so the POST handler can re-validate and issue the
    # code without re-parsing the original query string.
    hidden = "\n".join(
        f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v)}">'
        for k, v in {
            "client_id": params.client.client_id,
            "redirect_uri": params.redirect_uri,
            "response_type": "code",
            "code_challenge": params.code_challenge,
            "code_challenge_method": params.code_challenge_method,
            "state": params.state or "",
            "scope": params.scope or "",
        }.items()
    )
    err_html = (
        f'<p class="error" style="color:#b00020;margin:0 0 1em;">{html.escape(error)}</p>'
        if error else ""
    )
    body = f"""
<div class="container-narrow">
  <div class="hero">
    <h1>Authorize {html.escape(client_name)}</h1>
    <p class="sub" style="font-size:0.85em;background:#fff8e1;border:1px solid #f6c851;
                          border-radius:6px;padding:0.6em 0.8em;margin:1em 0;">
      <strong>Unverified client</strong> — geo-mcp does not vouch for the
      identity of the application requesting access. Only proceed if you
      recognise the redirect destination below.
    </p>
    <p class="sub"><strong>{html.escape(client_name)}</strong> is requesting access to
    your geo-mcp account. Paste your API key to approve — a new key will
    be minted and issued to this client so you can revoke it independently
    at any time.</p>
    <p class="sub" style="font-size:0.9em;">
      Approval will redirect to: <code><strong>{html.escape(redirect_host)}</strong></code>
      <br><span style="opacity:0.65;font-size:0.85em;">
        (full URL: <code>{html.escape(params.redirect_uri)}</code>)
      </span>
    </p>
    {err_html}
    <form method="POST" action="/oauth/authorize" style="margin-top:1.5em;">
      {hidden}
      <label for="api_key" style="display:block;margin-bottom:0.5em;">Your geo-mcp API key</label>
      <input type="password" id="api_key" name="api_key" required
             autocomplete="off"
             placeholder="gmcp_live_…"
             style="width:100%;padding:0.6em 0.8em;font-family:monospace;font-size:0.95em;border:1px solid #ccc;border-radius:6px;">
      <div style="margin-top:1em;display:flex;gap:0.6em;">
        <button type="submit" class="btn">Approve</button>
        <a class="btn btn-ghost" href="/">Cancel</a>
      </div>
    </form>
    <p class="sub" style="font-size:0.85em;margin-top:1.5em;">
      Don't have an API key? <a href="/signup">Sign up free</a> — one email, one key, no card.
    </p>
  </div>
</div>"""
    return _shell(f"Authorize {client_name} — geo-mcp", body)
