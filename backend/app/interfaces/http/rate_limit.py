"""In-process token-bucket rate limiting (ADR 0005 trade-off).

Per-replica, keyed by principal (when authenticated) or client IP. A shared limiter would need
a central store; we deliberately avoid extra infrastructure and accept per-replica limits,
documented as a known weakening. Auth/upload paths get a stricter bucket.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ...core.config import Settings
from .schemas.common import ProblemDetail


@dataclass
class _Bucket:
    tokens: float
    last: float
    capacity: float
    refill_per_sec: float

    def allow(self, now: float) -> bool:
        self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.refill_per_sec)
        self.last = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


@dataclass
class _Limiter:
    capacity: float
    refill_per_sec: float
    buckets: dict[str, _Bucket] = field(default_factory=dict)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self.buckets.get(key)
        if bucket is None:
            bucket = _Bucket(self.capacity, now, self.capacity, self.refill_per_sec)
            self.buckets[key] = bucket
        return bucket.allow(now)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._default = _Limiter(
            settings.rate_limit_per_minute, settings.rate_limit_per_minute / 60.0
        )
        self._strict = _Limiter(
            settings.upload_rate_limit_per_minute, settings.upload_rate_limit_per_minute / 60.0
        )

    def _client_key(self, request: Request) -> str:
        auth = request.headers.get("authorization")
        if auth:
            return f"tok:{hash(auth)}"
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"

    def _is_strict(self, request: Request) -> bool:
        path = request.url.path
        return path.endswith("/documents") and request.method == "POST" or "/auth/" in path

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.url.path in ("/health/live", "/health/ready", "/metrics"):
            return await call_next(request)
        limiter = self._strict if self._is_strict(request) else self._default
        if not limiter.allow(self._client_key(request)):
            body = ProblemDetail(
                title="Rate Limited", status=429, code="rate_limited",
                detail="too many requests; slow down",
                correlation_id=getattr(request.state, "correlation_id", None),
            )
            return JSONResponse(
                status_code=429, content=body.model_dump(exclude_none=True),
                media_type="application/problem+json",
            )
        return await call_next(request)
