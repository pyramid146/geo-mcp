from __future__ import annotations

import asyncpg

from geo_mcp.config import load_settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    # Use keyword args rather than the full DSN string so the password
    # doesn't end up in connection-time exception messages / tracebacks.
    global _pool
    if _pool is None:
        settings = load_settings()
        _pool = await asyncpg.create_pool(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            database=settings.db_name,
            min_size=1,
            max_size=10,
            command_timeout=5.0,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
