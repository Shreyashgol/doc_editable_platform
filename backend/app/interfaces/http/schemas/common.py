from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ProblemDetail(BaseModel):
    """RFC-9457 problem+json error body."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    code: str
    correlation_id: str | None = None
    errors: list[dict] | None = None


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, str] = Field(default_factory=dict)
