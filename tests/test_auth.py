from __future__ import annotations

import uuid

from geo_mcp.auth import (
    KEY_NAMESPACE,
    generate_key,
    hash_key,
    key_prefix,
    list_keys,
    mint_key,
    record_usage,
    revoke_key,
    validate_header,
)
from geo_mcp.data_access.postgis import get_pool

# asyncio_mode=auto is set in pyproject.toml, so async tests are auto-marked;
# pure sync tests in this file stay un-marked.


def _test_email() -> str:
    return f"test-{uuid.uuid4()}@example.test"


def test_generate_key_format():
    k = generate_key()
    assert k.startswith(KEY_NAMESPACE)
    # token_urlsafe(24) → 32 url-safe chars, no padding
    assert len(k) == len(KEY_NAMESPACE) + 32


def test_hash_key_is_stable_sha256_hex():
    h = hash_key("gmcp_live_sample")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
    assert h == hash_key("gmcp_live_sample")  # deterministic


def test_key_prefix_length():
    k = generate_key()
    assert len(key_prefix(k)) == 12
    assert k.startswith(key_prefix(k))


async def test_mint_and_validate_roundtrip():
    email = _test_email()
    raw, meta = await mint_key(email=email, label="roundtrip")
    assert meta["email"] == email
    assert meta["tier"] == "free"

    ctx = await validate_header(f"Bearer {raw}")
    assert ctx is not None
    assert str(ctx.api_key_id) == meta["key_id"]
    assert str(ctx.customer_id) == meta["customer_id"]
    assert ctx.tier == "free"


async def test_validate_missing_header_returns_none():
    assert await validate_header(None) is None
    assert await validate_header("") is None


async def test_validate_non_bearer_scheme_returns_none():
    raw, _ = await mint_key(email=_test_email())
    assert await validate_header(raw) is None  # no scheme
    assert await validate_header(f"Basic {raw}") is None  # wrong scheme


async def test_validate_unknown_key_returns_none():
    assert await validate_header("Bearer gmcp_live_not_a_real_key") is None


async def test_revoked_key_fails_validation():
    raw, meta = await mint_key(email=_test_email(), label="to-be-revoked")
    ok = await revoke_key(meta["key_id"])
    assert ok is True

    ctx = await validate_header(f"Bearer {raw}")
    assert ctx is None


async def test_record_usage_writes_row_and_bumps_last_used():
    email = _test_email()
    raw, meta = await mint_key(email=email, label="metering")
    ctx = await validate_header(f"Bearer {raw}")
    assert ctx is not None

    await record_usage(ctx, tool_name="transform_coords", duration_ms=7, status="ok")

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT tool_name, duration_ms, status, error_code
              FROM meta.usage_log
             WHERE api_key_id = $1
             ORDER BY called_at DESC LIMIT 1
            """,
            ctx.api_key_id,
        )
        key = await conn.fetchrow(
            "SELECT last_used_at FROM meta.api_keys WHERE id = $1",
            ctx.api_key_id,
        )

    assert row["tool_name"] == "transform_coords"
    assert row["duration_ms"] == 7
    assert row["status"] == "ok"
    assert row["error_code"] is None
    assert key["last_used_at"] is not None


async def test_list_keys_by_email():
    email = _test_email()
    _, meta1 = await mint_key(email=email, label="first")
    _, meta2 = await mint_key(email=email, label="second")

    rows = await list_keys(email=email)
    ids = {r["id"] for r in rows}
    assert {uuid.UUID(meta1["key_id"]), uuid.UUID(meta2["key_id"])} <= {uuid.UUID(str(i)) for i in ids}


# ---------------------------------------------------------------------------
# Pepper: peppered hashes are different from plain SHA-256, validation
# falls back to legacy SHA-256 so pre-pepper keys keep working after a
# pepper is introduced.
# ---------------------------------------------------------------------------


def test_hash_key_with_pepper_differs_from_legacy(monkeypatch):
    from geo_mcp import auth as auth_mod
    monkeypatch.setattr(auth_mod, "_KEY_PEPPER", b"secret-pepper-value")
    peppered = auth_mod.hash_key("gmcp_live_sample")
    legacy = auth_mod.legacy_hash_key("gmcp_live_sample")
    assert peppered != legacy
    # Both are sha256-hex, so same length
    assert len(peppered) == len(legacy) == 64


async def test_validate_accepts_legacy_hashed_key_when_pepper_enabled(monkeypatch):
    # Scenario: key was minted before pepper was set (stored as plain
    # sha256). Pepper is then introduced. The old key must still validate.
    from geo_mcp import auth as auth_mod

    # Mint a key WITHOUT pepper — it'll be stored with plain sha256.
    monkeypatch.setattr(auth_mod, "_KEY_PEPPER", b"")
    raw, meta = await mint_key(email=_test_email(), label="pre-pepper")

    # Now turn on the pepper (mimic an operator rolling it out).
    monkeypatch.setattr(auth_mod, "_KEY_PEPPER", b"new-production-pepper")

    ctx = await validate_header(f"Bearer {raw}")
    assert ctx is not None
    assert str(ctx.api_key_id) == meta["key_id"]


async def test_validate_accepts_peppered_key_when_pepper_enabled(monkeypatch):
    # New-minted key under pepper validates correctly.
    from geo_mcp import auth as auth_mod
    monkeypatch.setattr(auth_mod, "_KEY_PEPPER", b"production-pepper")
    raw, meta = await mint_key(email=_test_email(), label="post-pepper")
    ctx = await validate_header(f"Bearer {raw}")
    assert ctx is not None
    assert str(ctx.api_key_id) == meta["key_id"]
