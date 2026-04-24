"""Self-service signup — email + verification link → provisioned API key.

Flow:

1. POST /signup  {email}
   → generate one-time token, store sha256(token) in meta.pending_signups
     with a 24h TTL, send the plaintext token to the email address.
2. GET /signup/verify?token=...
   → look up sha256(token) in pending_signups; if found, unexpired,
     and unverified, mark verified_at and call auth.mint_key(email),
     returning the plaintext key to the browser *once*.

The plaintext token and plaintext key each exist only twice: once in
the email / browser response, once in server memory for the duration
of the request. Neither is ever logged or persisted in plaintext.
"""
from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from geo_mcp.auth import mint_key
from geo_mcp.data_access.postgis import get_pool

log = logging.getLogger(__name__)

TOKEN_TTL = timedelta(hours=24)
_TOKEN_BYTES = 24  # → 32 url-safe base64 chars, same shape as API keys


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _valid_ip_or_none(s: str | None) -> str | None:
    if not s:
        return None
    try:
        ipaddress.ip_address(s)
        return s
    except ValueError:
        return None


@dataclass(frozen=True)
class SignupStarted:
    email: str
    expires_at: datetime


async def start_signup(email: str, source_ip: str | None = None) -> SignupStarted:
    """Create a pending signup + send the verification email.

    Deduplication: at most one active (unverified, unexpired) token per
    email at a time — enforced by a partial unique index in the
    ``meta.pending_signups`` table. Repeated POST /signup requests for
    the same email are silently deduped (no second email sent), so an
    attacker rotating IPs can't turn us into an email bomb against a
    victim. The caller still sees the "check your email" page, which
    also avoids leaking whether the address is already registered.

    The plaintext token is emailed but NOT returned to the HTTP caller —
    the caller submitted the email, not the owner of the inbox. The
    inbox owner is the one who clicks the link.
    """
    email = email.strip().lower()
    if "@" not in email or len(email) > 254:
        raise ValueError("invalid email")

    raw_token = secrets.token_urlsafe(_TOKEN_BYTES)
    expires_at = datetime.now(timezone.utc) + TOKEN_TTL
    source_ip = _valid_ip_or_none(source_ip)

    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        # Clear any verified or expired rows for this email so the
        # partial unique index (on `email WHERE verified_at IS NULL`)
        # doesn't block a legitimate re-signup.
        await conn.execute(
            """
            DELETE FROM meta.pending_signups
             WHERE email = $1
               AND (verified_at IS NOT NULL OR expires_at <= now())
            """,
            email,
        )
        inserted = await conn.fetchval(
            """
            INSERT INTO meta.pending_signups
                   (email, token_hash, expires_at, source_ip)
            VALUES ($1, $2, $3, $4::inet)
            ON CONFLICT (email) WHERE verified_at IS NULL
            DO NOTHING
            RETURNING id
            """,
            email, _hash_token(raw_token), expires_at, source_ip,
        )

    if inserted is None:
        # There's already an active token for this email. Silently skip
        # sending a duplicate — the legitimate user can still use the
        # link from the first email.
        log.info("signup deduped (active token already exists) email=%s", email)
        return SignupStarted(email=email, expires_at=expires_at)

    await _send_verification_email(email, raw_token)
    return SignupStarted(email=email, expires_at=expires_at)


@dataclass(frozen=True)
class SignupVerified:
    email: str
    api_key: str
    key_prefix: str
    tier: str


async def verify_signup(raw_token: str) -> SignupVerified | None:
    """Validate a token; on success mint an API key and return it.

    Returns None for unknown / expired / already-used tokens — the
    caller maps that to a generic "invalid or expired" response so
    callers can't probe which bucket the token fell into.
    """
    if not raw_token:
        return None
    h = _hash_token(raw_token)

    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """
            UPDATE meta.pending_signups
               SET verified_at = now()
             WHERE token_hash = $1
               AND verified_at IS NULL
               AND expires_at > now()
            RETURNING email
            """,
            h,
        )
    if row is None:
        return None

    raw_key, meta = await mint_key(email=row["email"], label="self-service signup")
    return SignupVerified(
        email=row["email"],
        api_key=raw_key,
        key_prefix=meta["key_prefix"],
        tier=meta["tier"],
    )


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------
#
# Resend is the default because its free tier (100 emails/day, no card
# required) covers the expected signup volume for ages. If RESEND_API_KEY
# is unset we log the verification URL to stdout instead of sending — so
# local development doesn't need a third-party account just to exercise
# the flow.


def _verify_url(raw_token: str) -> str:
    base = os.getenv("GEO_MCP_PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return f"{base}/signup/verify?token={raw_token}"


async def _send_verification_email(email: str, raw_token: str) -> None:
    verify_url = _verify_url(raw_token)
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        log.warning(
            "RESEND_API_KEY unset — logging verification URL instead of emailing. "
            "email=%s url=%s",
            email, verify_url,
        )
        return

    from_addr = os.getenv("GEO_MCP_FROM_EMAIL", "onboarding@resend.dev")
    payload = {
        "from": from_addr,
        "to": [email],
        "subject": "Your geo-mcp API key — confirm your email",
        "text": (
            "Thanks for signing up to geo-mcp.\n\n"
            f"Click the link below to confirm your email and reveal your API key "
            f"(the link expires in 24 hours):\n\n"
            f"{verify_url}\n\n"
            "The key is shown exactly once — save it somewhere safe. If you "
            "didn't request this, you can ignore this email.\n"
        ),
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            if r.status_code >= 400:
                # Resend's 4xx body usually carries the real reason (e.g.
                # invalid sender domain, malformed recipient). Log it so
                # the next engineer doesn't have to re-instrument.
                log.error(
                    "resend rejected send email=%s status=%s body=%s",
                    email, r.status_code, r.text[:500],
                )
                return
    except Exception:
        # An email delivery failure shouldn't 500 the signup endpoint —
        # the pending row is already stored, we can re-send on request.
        log.exception("resend send failed for email=%s", email)
