"""FastAPI middleware — API key authentication, rate limiting, security headers, request logging."""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from threading import Lock

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.config.settings import get_settings

logger = logging.getLogger(__name__)

# Paths that don't require authentication
_PUBLIC_PATHS = frozenset({
    "/health", "/docs", "/openapi.json", "/redoc", "/", "/favicon.ico",
})


# ---------------------------------------------------------------------------
# Security Headers
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to every response.

    Includes Content-Security-Policy, X-Content-Type-Options,
    X-Frame-Options, Referrer-Policy, and Permissions-Policy.
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # CSP: allow self + inline styles/scripts for the UI
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        return response


# ---------------------------------------------------------------------------
# API Key Authentication
# ---------------------------------------------------------------------------

class APIKeyMiddleware(BaseHTTPMiddleware):
    """Validates the ``X-API-Key`` header against configured keys.

    Requests to public paths (health, docs) skip authentication.
    If no API keys are configured the middleware is permissive (dev mode).
    """

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()

        path = request.url.path
        # Skip auth for public endpoints, webhooks, and static assets
        if (
            path in _PUBLIC_PATHS
            or path.startswith("/webhook/")
            or path.startswith("/static/")
        ):
            return await call_next(request)

        # If no keys configured, allow all (development mode)
        if not settings.api_keys:
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "")
        if api_key not in settings.api_keys:
            logger.warning(
                "Unauthorized request to %s from %s",
                request.url.path,
                request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )

        return await call_next(request)


# ---------------------------------------------------------------------------
# Rate Limiting (sliding window counter per IP)
# ---------------------------------------------------------------------------

class _RateLimitBucket:
    """Thread-safe sliding window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: int = 60) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._lock = Lock()
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            timestamps = self._requests[key]
            # Prune old entries for this key
            cutoff = now - self._window
            self._requests[key] = [t for t in timestamps if t > cutoff]
            if len(self._requests[key]) >= self._max:
                return False
            self._requests[key].append(now)

            # Periodic cleanup: remove stale IP keys to prevent memory leak
            if len(self._requests) > 10_000:
                stale_keys = [
                    k for k, v in self._requests.items()
                    if not v or v[-1] < cutoff
                ]
                for k in stale_keys:
                    del self._requests[k]

            return True

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP sliding-window rate limiter."""

    def __init__(self, app: FastAPI, **kwargs) -> None:
        super().__init__(app, **kwargs)
        settings = get_settings()
        self._bucket = _RateLimitBucket(
            max_requests=settings.rate_limit_per_minute,
            window_seconds=60,
        )

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"

        if not self._bucket.is_allowed(client_ip):
            logger.warning("Rate limit exceeded for %s", client_ip)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
            )

        return await call_next(request)


# ---------------------------------------------------------------------------
# Request Logging with Correlation ID
# ---------------------------------------------------------------------------

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs every request with a correlation ID for tracing."""

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID", uuid.uuid4().hex[:16])
        start = time.monotonic()

        # Attach to request state for downstream use
        request.state.correlation_id = correlation_id

        response: Response = await call_next(request)

        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info(
            "request_id=%s method=%s path=%s status=%d duration_ms=%.1f",
            correlation_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        response.headers["X-Correlation-ID"] = correlation_id
        return response
