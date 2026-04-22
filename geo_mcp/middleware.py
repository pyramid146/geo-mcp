"""Auth + usage-logging middleware.

Two layers:

* ``AuthMiddleware`` — HTTP/ASGI, runs before MCP. Rejects any request
  without a valid ``Authorization: Bearer <key>`` header and stashes the
  resolved ``AuthContext`` into a ContextVar for downstream tool calls.
* ``UsageLoggingMiddleware`` — FastMCP-level, runs around every tool
  invocation. Reads the ContextVar, times the call, writes an
  ``meta.usage_log`` row, and bumps the key's ``last_used_at``.
"""
from __future__ import annotations

import logging
import time
from contextvars import ContextVar

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from geo_mcp.auth import AuthContext, record_usage, validate_header

log = logging.getLogger("geo_mcp.middleware")

# ContextVar populated by AuthMiddleware and read by UsageLoggingMiddleware.
# Default=None so unauthenticated code paths read cleanly if the var isn't set
# (e.g. in-process tool invocations during tests that bypass the HTTP layer).
current_auth: ContextVar[AuthContext | None] = ContextVar("current_auth", default=None)


# Paths that bypass API-key auth. Only GET endpoints that reveal no
# per-customer or operational secrets belong here — /health is the
# canonical example (just reports service liveness + table presence).
_PUBLIC_PATHS: frozenset[str] = frozenset({"/health"})


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
