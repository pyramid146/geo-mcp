"""End-to-end tests for the self-service signup flow.

Uses the real postgres to exercise the pending_signups row, and
monkeypatches ``_send_verification_email`` so nothing tries to hit
the Resend API. Round-trips via the captured plaintext token.
"""
from __future__ import annotations

import uuid

import pytest

from geo_mcp import signup as signup_mod
from geo_mcp.data_access.postgis import get_pool
from geo_mcp.signup import start_signup, verify_signup  # noqa: F401

pytestmark = pytest.mark.asyncio


@pytest.fixture
def capture_email(monkeypatch):
    captured: dict = {}

    async def _fake_send(email: str, raw_token: str) -> None:
        captured["email"] = email
        captured["token"] = raw_token

    monkeypatch.setattr(signup_mod, "_send_verification_email", _fake_send)
    return captured


async def test_signup_round_trip_mints_a_working_key(capture_email):
    email = f"signup-{uuid.uuid4()}@example.test"
    started = await start_signup(email)
    assert started.email == email
    assert capture_email["email"] == email
    token = capture_email["token"]
    assert token  # plaintext token was handed to the "email sender"

    result = await verify_signup(token)
    assert result is not None
    assert result.email == email
    assert result.api_key.startswith("gmcp_live_")
    assert result.tier == "free"

    # The key validates via the same hash lookup real traffic uses.
    from geo_mcp.auth import validate_header
    ctx = await validate_header(f"Bearer {result.api_key}")
    assert ctx is not None


async def test_verify_is_single_use(capture_email):
    email = f"signup-{uuid.uuid4()}@example.test"
    await start_signup(email)
    token = capture_email["token"]

    first = await verify_signup(token)
    assert first is not None

    # Second redemption must fail — verified_at is set, UPDATE matches nothing.
    second = await verify_signup(token)
    assert second is None


async def test_unknown_token_returns_none():
    assert await verify_signup("not-a-real-token") is None
    assert await verify_signup("") is None


async def test_expired_token_returns_none(capture_email):
    email = f"signup-{uuid.uuid4()}@example.test"
    await start_signup(email)
    token = capture_email["token"]

    # Fast-forward by expiring the row directly.
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE meta.pending_signups SET expires_at = now() - interval '1 hour' "
            "WHERE email = $1",
            email,
        )
    assert await verify_signup(token) is None


async def test_invalid_email_rejected(capture_email):
    with pytest.raises(ValueError):
        await start_signup("not-an-email")


async def test_email_is_normalised_to_lowercase(capture_email):
    email = f"SignUP-{uuid.uuid4()}@Example.TEST"
    started = await start_signup(email)
    assert started.email == email.lower()


async def test_duplicate_signup_within_window_skips_email(capture_email):
    # Email-bomb defence: a second signup for the same email while an
    # active token exists must not trigger a second email.
    email = f"dedupe-{uuid.uuid4()}@example.test"
    await start_signup(email)
    first_token = capture_email.get("token")
    assert first_token  # first send happened

    # Clear capture so we can detect a second send (or absence).
    capture_email.clear()

    r = await start_signup(email)  # same email, immediately
    assert r.email == email
    # Second call should NOT have invoked _send_verification_email.
    assert capture_email == {}


async def test_duplicate_signup_after_expiry_sends_fresh_email(capture_email):
    # Once a pending token expires, the same email should be allowed a
    # fresh send (partial unique index only applies to unverified rows,
    # and we clear expired rows explicitly before insert).
    email = f"expiry-{uuid.uuid4()}@example.test"
    await start_signup(email)
    assert capture_email.get("token")

    # Age the pending row so our "delete expired" path clears it.
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE meta.pending_signups SET expires_at = now() - interval '1 hour' WHERE email = $1",
            email,
        )

    capture_email.clear()
    await start_signup(email)
    # New token should have been issued + emailed.
    assert capture_email.get("token")
