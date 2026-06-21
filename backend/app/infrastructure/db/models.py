"""SQLAlchemy ORM models — the persistence shape, kept separate from domain entities.

Repositories translate between these and domain objects (see mappers.py). Keeping the two
apart means a schema change never forces a domain change and vice-versa (Clean Architecture).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin

EMBEDDING_DIM = 512


class UserModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    roles: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)


class DocumentModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("owner_id", "content_hash", name="uq_documents_owner_hash"),
        Index("ix_documents_owner_status", "owner_id", "status"),
    )

    owner_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    pages: Mapped[list[PageModel]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    job: Mapped[ProcessingJobModel | None] = relationship(
        back_populates="document", cascade="all, delete-orphan", uselist=False
    )


class PageModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_pages_doc_num"),)

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    width_px: Mapped[int] = mapped_column(Integer, nullable=False)
    height_px: Mapped[int] = mapped_column(Integer, nullable=False)
    dpi: Mapped[int] = mapped_column(Integer, nullable=False)
    render_uri: Mapped[str] = mapped_column(Text, nullable=False)

    document: Mapped[DocumentModel] = relationship(back_populates="pages")


class ProcessingJobModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "processing_jobs"

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    stage_status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    timings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped[DocumentModel] = relationship(back_populates="job")


class SymbolModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "symbols"
    __table_args__ = (
        Index("ix_symbols_doc_page", "document_id", "page_number"),
        Index("ix_symbols_type", "type"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False, default="Unknown")
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    bbox_x: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_w: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_h: Mapped[float] = mapped_column(Float, nullable=False)
    centroid_x: Mapped[float] = mapped_column(Float, nullable=False)
    centroid_y: Mapped[float] = mapped_column(Float, nullable=False)
    rotation: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    crop_uri: Mapped[str] = mapped_column(Text, nullable=False)
    classification_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    properties: Mapped[list[SymbolPropertyModel]] = relationship(
        back_populates="symbol", cascade="all, delete-orphan"
    )
    embedding: Mapped[EmbeddingModel | None] = relationship(
        back_populates="symbol", cascade="all, delete-orphan", uselist=False
    )


class SymbolPropertyModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "symbol_properties"
    __table_args__ = (UniqueConstraint("symbol_id", "key", name="uq_symbol_property_key"),)

    symbol_id: Mapped[UUID] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)

    symbol: Mapped[SymbolModel] = relationship(back_populates="properties")


class SymbolVersionModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "symbol_versions"
    __table_args__ = (UniqueConstraint("symbol_id", "version", name="uq_symbol_version"),)

    symbol_id: Mapped[UUID] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    changed_by: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)


class EmbeddingModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "embeddings"

    symbol_id: Mapped[UUID] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)

    symbol: Mapped[SymbolModel] = relationship(back_populates="embedding")


class RelationshipModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "relationships"
    __table_args__ = (
        Index("ix_rel_source", "source_symbol_id"),
        Index("ix_rel_target", "target_symbol_id"),
        Index("ix_rel_doc_type", "document_id", "type"),
        CheckConstraint("source_symbol_id <> target_symbol_id", name="ck_rel_no_self_loop"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    source_symbol_id: Mapped[UUID] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False
    )
    target_symbol_id: Mapped[UUID] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class PipelineTaskModel(UUIDMixin, TimestampMixin, Base):
    """Durable job-queue row (ADR 0005). One row per (document, stage); retries reuse the row."""

    __tablename__ = "pipeline_tasks"
    __table_args__ = (
        UniqueConstraint("document_id", "stage", name="uq_task_doc_stage"),
        # The hot path: find due, pending tasks ordered by run_after.
        Index("ix_tasks_claim", "status", "run_after"),
        Index("ix_tasks_locked", "locked_at"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class AuditLogModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_correlation", "correlation_id"),
    )

    actor_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
