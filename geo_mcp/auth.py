"""API key minting, hashing, validation, and usage logging.

Key format:  ``gmcp_live_<32 url-safe base64 chars>``.
Storage:     SHA-256 hex of the full plaintext key (`key_hash`), plus the
             plaintext first 12 chars (`key_prefix`) for UI display.
             The plaintext key itself is never stored; it is shown to the
             human *once*, at creation time.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from geo_mcp.data_access.postgis import get_pool

KEY_NAMESPACE: str = "gmcp_live_"
_KEY_BODY_BYTES: int = 24  # → 32 url-safe base64 chars
_KEY_PREFIX_LEN: int = 12  # first N chars of plaintext, safe to show


def generate_key() -> str:
    return KEY_NAMESPACE + secrets.token_urlsafe(_KEY_BODY_BYTES)


def hash_key(raw: str) -> str:
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
    lazily by ``record_usage`` so protocol-level pings don't produce writes."""
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    raw = parts[1]
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT k.id, k.customer_id, c.tier
              FROM meta.api_keys k
              JOIN meta.customers c ON c.id = k.customer_id
             WHERE k.key_hash = $1 AND k.revoked_at IS NULL
            """,
            hash_key(raw),
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
