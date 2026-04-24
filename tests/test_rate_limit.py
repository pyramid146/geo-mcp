"""Tests for RateLimitMiddleware.

Exercises the middleware logic directly — no Starlette app, no FastMCP
runtime. We set ``current_auth`` in the ContextVar, then call the
middleware's ``on_call_tool`` in a loop and assert that the N+1-th call
raises ``RateLimitExceeded``.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from geo_mcp.auth import AuthContext
from geo_mcp.middleware import (
    RateLimitExceeded,
    RateLimitMiddleware,
    _RATE_LIMITS,
    current_auth,
)

pytestmark = pytest.mark.asyncio


def _fake_ctx(tool_name: str = "flood_risk_uk"):
    return SimpleNamespace(message=SimpleNamespace(name=tool_name))


async def _call_next(_ctx):
    return {"ok": True}


async def test_under_limit_calls_pass_through():
    mw = RateLimitMiddleware()
    auth = AuthContext(api_key_id=uuid4(), customer_id=uuid4(), tier="free")
    token = current_auth.set(auth)
    try:
        for _ in range(_RATE_LIMITS["free"]):
            r = await mw.on_call_tool(_fake_ctx(), _call_next)
            assert r == {"ok": True}
    finally:
        current_auth.reset(token)


async def test_over_limit_raises_rate_limit_exceeded():
    mw = RateLimitMiddleware()
    auth = AuthContext(api_key_id=uuid4(), customer_id=uuid4(), tier="free")
    token = current_auth.set(auth)
    try:
        # Exhaust the free-tier budget.
        for _ in range(_RATE_LIMITS["free"]):
            await mw.on_call_tool(_fake_ctx(), _call_next)
        # The next call crosses the threshold.
        with pytest.raises(RateLimitExceeded) as exc:
            await mw.on_call_tool(_fake_ctx(), _call_next)
        assert "Retry in" in str(exc.value)
        assert "free" in str(exc.value)
    finally:
        current_auth.reset(token)


async def test_hobby_tier_has_higher_limit():
    mw = RateLimitMiddleware()
    auth = AuthContext(api_key_id=uuid4(), customer_id=uuid4(), tier="hobby")
    token = current_auth.set(auth)
    try:
        # Hobby limit is well above free — 31 calls should be fine.
        for _ in range(_RATE_LIMITS["free"] + 1):
            await mw.on_call_tool(_fake_ctx(), _call_next)
    finally:
        current_auth.reset(token)


async def test_different_keys_are_isolated():
    mw = RateLimitMiddleware()
    key_a = AuthContext(api_key_id=uuid4(), customer_id=uuid4(), tier="free")
    key_b = AuthContext(api_key_id=uuid4(), customer_id=uuid4(), tier="free")

    # Exhaust key A's budget.
    token = current_auth.set(key_a)
    try:
        for _ in range(_RATE_LIMITS["free"]):
            await mw.on_call_tool(_fake_ctx(), _call_next)
    finally:
        current_auth.reset(token)

    # Key B should still have a full allowance.
    token = current_auth.set(key_b)
    try:
        r = await mw.on_call_tool(_fake_ctx(), _call_next)
        assert r == {"ok": True}
    finally:
        current_auth.reset(token)


async def test_no_auth_context_falls_through():
    # In-process / unauthenticated callers (e.g. tests that bypass HTTP)
    # shouldn't be rate-limited.
    mw = RateLimitMiddleware()
    # current_auth default is None
    for _ in range(_RATE_LIMITS["free"] + 50):
        r = await mw.on_call_tool(_fake_ctx(), _call_next)
        assert r == {"ok": True}


async def test_unknown_tier_defaults_to_free_limit():
    mw = RateLimitMiddleware()
    auth = AuthContext(api_key_id=uuid4(), customer_id=uuid4(), tier="enterprise")
    token = current_auth.set(auth)
    try:
        # Unknown tier falls back to _DEFAULT_RATE_LIMIT (= free: 30).
        for _ in range(_RATE_LIMITS["free"]):
            await mw.on_call_tool(_fake_ctx(), _call_next)
        with pytest.raises(RateLimitExceeded):
            await mw.on_call_tool(_fake_ctx(), _call_next)
    finally:
        current_auth.reset(token)
