"""Structured logging + correlation-id context.

structlog renders JSON in non-local environments so logs are machine-parseable. A contextvar
carries the correlation/request id so every log line (API and worker) for one document's journey
is linkable. Secret redaction runs as a processor so credentials never reach the log store.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

import structlog

correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)

_REDACT_KEYS = {"password", "password_hash", "jwt_secret", "secret_key", "authorization", "token"}


def _add_correlation_id(_logger: object, _name: str, event_dict: dict) -> dict:
    cid = correlation_id_ctx.get()
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def _redact_secrets(_logger: object, _name: str, event_dict: dict) -> dict:
    for key in list(event_dict):
        if key.lower() in _REDACT_KEYS:
            event_dict[key] = "***redacted***"
    return event_dict


def configure_logging(*, level: str = "INFO", json: bool = True) -> None:
    logging.basicConfig(format="%(message)s", level=getattr(logging, level.upper(), logging.INFO))
    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_correlation_id,
        _redact_secrets,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
