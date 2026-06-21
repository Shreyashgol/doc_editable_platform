from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from ....domain.entities import Document, ProcessingJob


class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    status: str
    page_count: int
    size_bytes: int
    mime_type: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, doc: Document) -> DocumentResponse:
        return cls(
            id=doc.id,
            filename=doc.filename,
            status=doc.status.value,
            page_count=doc.page_count,
            size_bytes=doc.size_bytes,
            mime_type=doc.mime_type,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )


class UploadResponse(BaseModel):
    id: UUID
    status: str
    deduplicated: bool
    status_url: str


class JobView(BaseModel):
    stage: str
    stage_status: str
    attempts: int
    max_attempts: int
    last_error: str | None
    timings: dict[str, float]


class DocumentStatusResponse(BaseModel):
    id: UUID
    status: str
    page_count: int
    job: JobView | None

    @classmethod
    def from_domain(cls, doc: Document, job: ProcessingJob | None) -> DocumentStatusResponse:
        return cls(
            id=doc.id,
            status=doc.status.value,
            page_count=doc.page_count,
            job=(
                JobView(
                    stage=job.stage.value,
                    stage_status=job.stage_status,
                    attempts=job.attempts,
                    max_attempts=job.max_attempts,
                    last_error=job.last_error,
                    timings=job.timings,
                )
                if job
                else None
            ),
        )
