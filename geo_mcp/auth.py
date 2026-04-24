"""API key minting, hashing, validation, and usage logging.

Key format:  ``gmcp_live_<32 url-safe base64 chars>`` — 192 bits of entropy
             from ``secrets.token_urlsafe(24)``.
Storage:     HMAC-SHA256(pepper, raw).hexdigest if ``GEO_MCP_KEY_PEPPER`` is
             set; plain SHA-256 otherwise. Stored in ``meta.api_keys.key_hash``
             alongside the plaintext first 12 chars (``key_prefix``) for UI
             display. The plaintext key itself is never stored — it's shown
             to the human *once*, at creation time.

Pepper:      An optional server-side secret loaded from the
             ``GEO_MCP_KEY_PEPPER`` env var. When set, keys are stored
             as HMAC(pepper, raw) so a leaked backup (or a compromised
             DB snapshot) can't be brute-forced offline without also
             possessing the pepper. When unset, the code falls back to
             plain SHA-256 — meaning dev/test instances and existing
             deployments keep working unchanged.

Backwards compatibility: ``validate_header`` tries BOTH the peppered
hash and the legacy plain-SHA256 hash on lookup. This way, existing
keys continue to validate even after a pepper is introduced; they can
be rotated to peppered hashes at the user's convenience.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from geo_mcp.data_access.postgis import get_pool

KEY_NAMESPACE: str = "gmcp_live_"
_KEY_BODY_BYTES: int = 24  # → 32 url-safe base64 chars
_KEY_PREFIX_LEN: int = 12  # first N chars of plaintext, safe to show

# Loaded once at import time. Changing the pepper after keys have been
# minted without it will require re-issuing those keys (or leaving them
# on the legacy-hash fallback path).
_KEY_PEPPER = os.environ.get("GEO_MCP_KEY_PEPPER", "").encode("utf-8")


def generate_key() -> str:
    return KEY_NAMESPACE + secrets.token_urlsafe(_KEY_BODY_BYTES)


def hash_key(raw: str) -> str:
    """Canonical hash used for NEW keys. HMAC-SHA256 with the pepper if
    one is configured; plain SHA-256 otherwise."""
    raw_b = raw.encode("utf-8")
    if _KEY_PEPPER:
        return hmac.new(_KEY_PEPPER, raw_b, hashlib.sha256).hexdigest()
    return hashlib.sha256(raw_b).hexdigest()


def _legacy_hash_key(raw: str) -> str:
    """Plain SHA-256 — the hashing used before pepper support existed.
    Kept as a fallback on ``validate_header`` so pre-pepper keys still
    authenticate after the pepper is introduced."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def key_prefix(raw: str) -> str:
    return raw[:_KEY_PREFIX_LEN]


@dataclass(frozen=True)
class AuthContext:
    api_key_id: UUID
    customer_id: UUID
    tier: str


async def mint_key(email: str, label: str | None = None) -> tuple[str, dict[str, Any]]:
    """Create (or reuse) a customer by email, mint a new API key, return
    the plaintext key plus metadata. The plaintext key is shown exactly once;
    only its sha256 + prefix are persisted."""
    raw = generate_key()
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        cust = await conn.fetchrow(
            """
            INSERT INTO meta.customers (email) VALUES ($1)
            ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
            RETURNING id, email, tier, created_at
            """,
            email,
        )
        row = await conn.fetchrow(
            """
            INSERT INTO meta.api_keys (customer_id, key_hash, key_prefix, label)
            VALUES ($1, $2, $3, $4)
            RETURNING id, key_prefix, created_at
            """,
            cust["id"], hash_key(raw), key_prefix(raw), label,
        )
    return raw, {
        "customer_id": str(cust["id"]),
        "email": cust["email"],
        "tier": cust["tier"],
        "key_id": str(row["id"]),
        "key_prefix": row["key_prefix"],
        "label": label,
        "created_at": row["created_at"].isoformat(),
    }


async def validate_header(authorization: str | None) -> AuthContext | None:
    """Parse ``Authorization: Bearer <key>``, look up by hash, return the
    auth context or None. No ``last_used_at`` update here — that's done
    lazily by ``record_usage`` so protocol-level pings don't produce writes.

    When a pepper is configured, checks both the peppered (current) and
    legacy (plain SHA-256) hashes so keys minted before the pepper was
    introduced continue to work.
    """
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    raw = parts[1]

    # Try the canonical hash first; if that misses and a pepper is in
    # use, try the legacy plain-SHA256 hash as a backwards-compat fallback.
    candidates = [hash_key(raw)]
    if _KEY_PEPPER:
        candidates.append(_legacy_hash_key(raw))

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT k.id, k.customer_id, c.tier
              FROM meta.api_keys k
              JOIN meta.customers c ON c.id = k.customer_id
             WHERE k.key_hash = ANY($1::text[]) AND k.revoked_at IS NULL
             LIMIT 1
            """,
            candidates,
        )
    if row is None:
        return None
    return AuthContext(api_key_id=row["id"], customer_id=row["customer_id"], tier=row["tier"])


async def record_usage(
    ctx: AuthContext,
    tool_name: str,
    duration_ms: int,
    status: str,
    error_code: str | None = None,
) -> None:
    """Log one tool call and bump the key's last_used_at in a single
    transaction."""
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            """
            INSERT INTO meta.usage_log
                   (api_key_id, customer_id, tool_name, duration_ms, status, error_code)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            ctx.api_key_id, ctx.customer_id, tool_name, duration_ms, status, error_code,
        )
        await conn.execute(
            "UPDATE meta.api_keys SET last_used_at = now() WHERE id = $1",
            ctx.api_key_id,
        )


async def list_keys(email: str | None = None) -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if email:
            rows = await conn.fetch(
                """
                SELECT k.id, k.key_prefix, k.label, k.created_at, k.last_used_at,
                       k.revoked_at, c.email, c.tier
                  FROM meta.api_keys k
                  JOIN meta.customers c ON c.id = k.customer_id
                 WHERE c.email = $1
                 ORDER BY k.created_at DESC
                """,
                email,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT k.id, k.key_prefix, k.label, k.created_at, k.last_used_at,
                       k.revoked_at, c.email, c.tier
                  FROM meta.api_keys k
                  JOIN meta.customers c ON c.id = k.customer_id
                 ORDER BY k.created_at DESC
                """
            )
    return [dict(r) for r in rows]


async def revoke_key(key_id: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE meta.api_keys SET revoked_at = now() WHERE id = $1::uuid AND revoked_at IS NULL",
            key_id,
        )
    # asyncpg execute returns "UPDATE N"
    return result.endswith(" 1")
