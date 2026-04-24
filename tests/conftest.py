"""Shared pytest fixtures for the geo-mcp test suite.

Session-scoped cleanup sweep: the test fixtures in test_auth.py,
test_signup.py, test_signup_routes.py, and test_middleware.py create
customer / api_key / usage_log / pending_signups rows against the live
`meta` schema (no test-DB isolation yet). Without this fixture those
rows accumulate forever — running the suite monthly would seed
thousands of junk rows into `meta.customers`.

We use the reserved `.test` TLD (RFC 2606) for every fixture-generated
email, so the cleanup pattern `%@example.test` is safe: no real user's
address can match. DELETEs run as `mcp_admin` because `mcp_readonly`
(the app role) lacks DELETE on most meta tables — tests shouldn't
require the app role to gain destructive privileges in production.

If the cleanup fails it's logged but not raised, so a broken teardown
can never mask genuine test failures.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg
import pytest
from dotenv import load_dotenv


_REPO_ROOT = Path(__file__).resolve().parent.parent


async def _sweep_test_rows() -> dict[str, int]:
    """Delete all `%@example.test` rows from the meta schema. FK order:
    usage_log → api_keys → pending_signups → customers."""
    load_dotenv(_REPO_ROOT / ".env", override=False)
    conn = await asyncpg.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "5432")),
        user="mcp_admin",
        password=os.environ["MCP_ADMIN_PASSWORD"],
        database=os.environ["POSTGRES_DB"],
        timeout=5.0,
    )
    deleted: dict[str, int] = {}
    try:
        async with conn.transaction():
            for sql, key in (
                ("""
                 DELETE FROM meta.usage_log
                  WHERE customer_id IN (
                      SELECT id FROM meta.customers WHERE email LIKE '%@example.test'
                  )
                 """, "usage_log"),
                # OAuth auth-codes reference api_keys(granter) + customers —
                # wipe before api_keys so the FK doesn't block the cascade.
                ("""
                 DELETE FROM meta.oauth_auth_codes
                  WHERE customer_id IN (
                      SELECT id FROM meta.customers WHERE email LIKE '%@example.test'
                  )
                 """, "oauth_auth_codes"),
                ("""
                 DELETE FROM meta.api_keys
                  WHERE customer_id IN (
                      SELECT id FROM meta.customers WHERE email LIKE '%@example.test'
                  )
                 """, "api_keys"),
                ("""
                 DELETE FROM meta.pending_signups
                  WHERE email LIKE '%@example.test'
                 """, "pending_signups"),
                # OAuth clients are test-created; we label them with
                # 'test-oauth-' prefixes and clean up on that.
                ("""
                 DELETE FROM meta.oauth_clients
                  WHERE name LIKE 'test-oauth-%'
                 """, "oauth_clients"),
                ("""
                 DELETE FROM meta.customers WHERE email LIKE '%@example.test'
                 """, "customers"),
            ):
                status = await conn.execute(sql)
                # asyncpg execute returns e.g. "DELETE 7"
                try:
                    deleted[key] = int(status.rsplit(" ", 1)[-1])
                except ValueError:
                    deleted[key] = 0
    finally:
        await conn.close()
    return deleted


@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    """The signup/oauth-register IP rate limit is process-global in-memory
    state. Without this fixture, a long test run eventually trips 429s
    because every test appears to come from the same client host. The
    production runtime never sees this pattern (no single IP makes 5
    signups / register calls per hour in practice)."""
    from geo_mcp import server as server_mod
    server_mod._rate_hits.clear()
    yield


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_meta_rows():
    yield
    try:
        deleted = asyncio.run(_sweep_test_rows())
        total = sum(deleted.values())
        if total:
            print(
                f"\n[conftest] cleaned up {total} @example.test rows "
                f"({deleted})"
            )
    except Exception as exc:  # noqa: BLE001
        # Never let cleanup failure mask real test failures.
        print(f"\n[conftest] test-meta cleanup failed: {exc!r}")


# ---------------------------------------------------------------------------
# Per-test asyncpg pool reset.
# ---------------------------------------------------------------------------
# The asyncpg pool is a process-wide singleton in
# geo_mcp.data_access.postgis. Tests running under different event
# loops without this fixture hit "Event loop is closed" errors on the
# second test in a file.
#
# Previously every test module declared its own copy. Centralised here
# so every test file gets it via autouse. A module that deliberately
# wants to keep the pool alive between tests can override with its own
# fixture of the same name.


@pytest.fixture(autouse=True)
async def _reset_pool():
    from geo_mcp.data_access.postgis import close_pool  # local import
    yield
    await close_pool()
