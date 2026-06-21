"""Async SQLAlchemy engine/session wiring and the declarative base.

The async engine backs the API; Alembic uses the sync URL. ``created_at``/``updated_at`` are
provided by a mixin and maintained in Python (and by a DB trigger in the migration) so every
table satisfies the cross-cutting convention from the design docs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ...core.config import Settings


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class UUIDMixin:
    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)


def create_engine_and_sessionmaker(
    settings: Settings,
) -> tuple[object, async_sessionmaker[AsyncSession]]:
    connect_args: dict[str, object] = {}
    if settings.db_require_ssl:
        # asyncpg takes ``ssl`` (not the libpq ``sslmode`` query param). Neon's PgBouncer
        # pooler is incompatible with prepared-statement caching, so disable it.
        connect_args["ssl"] = True
        connect_args["statement_cache_size"] = 0
    engine = create_async_engine(
        str(settings.database_url),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        future=True,
        connect_args=connect_args,
    )
    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession, autoflush=False
    )
    return engine, session_factory
