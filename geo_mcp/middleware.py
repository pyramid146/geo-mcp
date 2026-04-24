"""Auth + usage-logging + rate-limit middleware.

Three layers:

* ``AuthMiddleware`` — HTTP/ASGI, runs before MCP. Rejects any request
  without a valid ``Authorization: Bearer <key>`` header and stashes the
  resolved ``AuthContext`` into a ContextVar for downstream tool calls.
* ``UsageLoggingMiddleware`` — FastMCP-level, runs around every tool
  invocation. Reads the ContextVar, times the call, writes an
  ``meta.usage_log`` row, and bumps the key's ``last_used_at``.
* ``RateLimitMiddleware`` — FastMCP-level, per-``api_key_id`` fixed-window
  counter. Raises ``RateLimitExceeded`` on the first call over the
  window, which the usage-logging layer records as status='error' and
  the MCP client sees as a tool-call failure.
"""
from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from uuid import UUID

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from geo_mcp.auth import AuthContext, record_usage, validate_header

log = logging.getLogger(__name__)

# ContextVar populated by AuthMiddleware and read by UsageLoggingMiddleware.
# Default=None so unauthenticated code paths read cleanly if the var isn't set
# (e.g. in-process tool invocations during tests that bypass the HTTP layer).
current_auth: ContextVar[AuthContext | None] = ContextVar("current_auth", default=None)


# Paths that bypass API-key auth. Only endpoints that reveal no
# per-customer or operational secrets belong here: /health (liveness
# probe), the root landing page, and the self-service signup + verify
# endpoints — those *are* what mints a key, so can't require one.
_PUBLIC_PATHS: frozenset[str] = frozenset({
    "/", "/health", "/status", "/status.json", "/signup", "/signup/verify", "/favicon.svg",
})


class AuthMiddleware(BaseHTTPMiddleware):
    """Validate ``Authorization: Bearer <key>`` per request.

    Public paths in ``_PUBLIC_PATHS`` bypass auth — they must not leak
    anything an unauthenticated caller shouldn't see.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        authorization = request.headers.get("authorization")
        ctx = await validate_header(authorization)
        if ctx is None:
            return JSONResponse(
                {"error": "unauthorized", "message": "Missing or invalid Bearer API key."},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="geo-mcp"'},
            )
        token = current_auth.set(ctx)
        try:
            return await call_next(request)
        finally:
            current_auth.reset(token)


class UsageLoggingMiddleware(Middleware):
    """Meter every authenticated tool call into ``meta.usage_log``."""

    async def on_call_tool(
        self,
        context: MiddlewareContext,
        call_next: CallNext,
    ):
        auth = current_auth.get()
        tool_name = getattr(context.message, "name", None) or "unknown"
        start = time.perf_counter()

        try:
            result = await call_next(context)
        except RateLimitExceeded:
            duration_ms = int((time.perf_counter() - start) * 1000)
            await _safe_record(auth, tool_name, duration_ms, "error", "rate_limited")
            raise
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            await _safe_record(auth, tool_name, duration_ms, "error", type(exc).__name__)
            raise

        duration_ms = int((time.perf_counter() - start) * 1000)
        await _safe_record(auth, tool_name, duration_ms, "ok", None)
        return result


async def _safe_record(
    auth: AuthContext | None,
    tool_name: str,
    duration_ms: int,
    status: str,
    error_code: str | None,
) -> None:
    if auth is None:
        # In-process call (tests) or unauthenticated edge — shouldn't happen
        # under the HTTP server once AuthMiddleware is wired in.
        return
    try:
        await record_usage(auth, tool_name, duration_ms, status, error_code)
    except Exception:
        # Usage logging must never break a tool call for the caller.
        log.exception("failed to log usage for tool=%s status=%s", tool_name, status)


# ---------------------------------------------------------------------------
# Rate limiting (per api_key_id, tier-dependent, fixed 60-second windows).
# ---------------------------------------------------------------------------
# In-memory process-local counters — fine for the single-node MVP.
# Horizontal scaling would lift this into Postgres or Redis. Resetting
# on a per-minute boundary is simpler than a token bucket and gives
# close-enough behaviour for "prevent a runaway client from burying us
# in a second". Limits are deliberately generous so legit agents aren't
# surprised; the purpose is to blunt abuse, not meter usage (that's
# meta.usage_log's job).

_RATE_LIMITS: dict[str, int] = {
    # calls per minute, per key
    "free":  30,
    "hobby": 300,
    "pro":   3000,
    "team":  30000,
}
_DEFAULT_RATE_LIMIT = 30


class RateLimitExceeded(Exception):
    """Raised when an API key exceeds its per-minute call ceiling.

    Surfaces to the MCP client as a tool-call failure. The UsageLoggingMiddleware
    records the rejection as status='error', error_code='rate_limited' so
    abusers are visible in the usage log for follow-up.
    """


class RateLimitMiddleware(Middleware):
    """Per-key fixed-window rate limit.

    Reads the ``AuthContext`` from the ``current_auth`` ContextVar.
    Falls through without limiting if no auth context (in-process /
    unauthenticated). Order relative to ``UsageLoggingMiddleware``: put
    this one INSIDE (add it AFTER UsageLogging in the add_middleware
    sequence) so rejected calls still land in ``meta.usage_log``.
    """

    def __init__(self) -> None:
        # api_key_id → (window_start_minute, count_in_window)
        self._counters: dict[UUID, tuple[int, int]] = {}

    async def on_call_tool(
        self,
        context: MiddlewareContext,
        call_next: CallNext,
    ):
        auth = current_auth.get()
        if auth is None:
            return await call_next(context)

        limit = _RATE_LIMITS.get(auth.tier, _DEFAULT_RATE_LIMIT)
        now_min = int(time.time() // 60)
        window_start, count = self._counters.get(auth.api_key_id, (now_min, 0))
        if window_start != now_min:
            window_start, count = now_min, 0
        count += 1
        self._counters[auth.api_key_id] = (window_start, count)

        if count > limit:
            retry_after = 60 - (int(time.time()) % 60)
            log.warning(
                "rate_limited api_key_id=%s tier=%s count=%d limit=%d",
                auth.api_key_id, auth.tier, count, limit,
            )
            raise RateLimitExceeded(
                f"Rate limit exceeded for tier {auth.tier!r}: "
                f"{limit} calls per minute. Retry in {retry_after}s."
            )

        return await call_next(context)
