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
