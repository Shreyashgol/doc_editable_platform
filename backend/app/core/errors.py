"""Typed exception hierarchy.

Domain and application code raise these framework-free exceptions. A single HTTP middleware
(interfaces layer) maps them to RFC-9457 problem+json responses, and Celery's base task maps
them to retry/DLQ decisions. Nothing here imports FastAPI.
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for all expected application errors.

    Attributes:
        code: stable, machine-readable identifier (clients switch on this, not on prose).
        message: human-readable detail.
        http_status: suggested HTTP status for the delivery layer.
        retryable: whether a worker stage raising this should be retried.
    """

    code: str = "internal_error"
    http_status: int = 500
    retryable: bool = False

    def __init__(self, message: str | None = None, *, retryable: bool | None = None) -> None:
        self.message = message or self.__class__.__doc__ or self.code
        if retryable is not None:
            self.retryable = retryable
        super().__init__(self.message)


# --- 4xx: client / validation ---
class ValidationError(AppError):
    """Request or input failed validation."""

    code = "validation_error"
    http_status = 422


class NotFoundError(AppError):
    """Requested resource does not exist."""

    code = "not_found"
    http_status = 404


class ConflictError(AppError):
    """Resource conflict (e.g., duplicate upload, version clash)."""

    code = "conflict"
    http_status = 409


class AuthenticationError(AppError):
    """Missing or invalid credentials."""

    code = "unauthenticated"
    http_status = 401


class AuthorizationError(AppError):
    """Authenticated but not permitted (RBAC / ownership)."""

    code = "forbidden"
    http_status = 403


class RateLimitError(AppError):
    """Too many requests."""

    code = "rate_limited"
    http_status = 429


# --- File / security specific ---
class FileValidationError(ValidationError):
    """Uploaded file failed structural/security validation."""

    code = "file_validation_error"


class PdfBombError(FileValidationError):
    """PDF exceeded page/pixel/stream safety limits (possible decompression bomb)."""

    code = "pdf_bomb_detected"


class VirusDetectedError(FileValidationError):
    """Uploaded file flagged by the virus scanner."""

    code = "virus_detected"


# --- Domain invariants ---
class IllegalStateTransitionError(ConflictError):
    """Attempted an invalid document state-machine transition."""

    code = "illegal_state_transition"


# --- 5xx: infrastructure (generally retryable in workers) ---
class InfrastructureError(AppError):
    """Failure in an external dependency (DB, broker, storage, model)."""

    code = "infrastructure_error"
    http_status = 503
    retryable = True


class ProcessingError(AppError):
    """A pipeline stage failed to process its input."""

    code = "processing_error"
    http_status = 500
    retryable = True
