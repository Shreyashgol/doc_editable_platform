"""Cross-cutting HTTP middleware: correlation id, secure headers, and the typed-error handler."""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ...core.errors import AppError
from ...core.logging import correlation_id_ctx, get_logger
from .schemas.common import ProblemDetail

_log = get_logger("http")

CORRELATION_HEADER = "X-Correlation-ID"

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        cid = request.headers.get(CORRELATION_HEADER) or uuid.uuid4().hex
        token = correlation_id_ctx.set(cid)
        request.state.correlation_id = cid
        try:
            response = await call_next(request)
        finally:
            correlation_id_ctx.reset(token)
        response.headers[CORRELATION_HEADER] = cid
        return response


class SecureHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        for key, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response


def _problem(
    status: int,
    title: str,
    code: str,
    detail: str,
    cid: str | None,
    errors: list[dict] | None = None,
) -> JSONResponse:
    body = ProblemDetail(
        title=title, status=status, code=code, detail=detail, correlation_id=cid, errors=errors
    )
    return JSONResponse(
        status_code=status,
        content=body.model_dump(exclude_none=True),
        media_type="application/problem+json",
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        cid = getattr(request.state, "correlation_id", None)
        if exc.http_status >= 500:
            _log.error("app_error", code=exc.code, detail=exc.message)
        return _problem(
            exc.http_status, exc.code.replace("_", " ").title(), exc.code, exc.message, cid
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        cid = getattr(request.state, "correlation_id", None)
        _log.exception("unhandled_exception", error=str(exc))
        return _problem(
            500, "Internal Server Error", "internal_error", "an unexpected error occurred", cid
        )


def register_middleware(app: FastAPI, settings) -> None:  # type: ignore[no-untyped-def]
    # Added inner-first: execution order is CorrelationId (outermost) -> SecureHeaders ->
    # RateLimit -> Metrics (innermost), so a rate-limited response still carries a correlation id.
    from .rate_limit import RateLimitMiddleware

    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(SecureHeadersMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
