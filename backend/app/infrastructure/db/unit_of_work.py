"""SQLAlchemy Unit of Work: one AsyncSession per use case, wiring all repository adapters."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...application.unit_of_work import UnitOfWork
from ...core.config import Settings
from ..messaging.event_publisher import PostgresEventPublisher
from ..queue.postgres_queue import SqlAlchemyTaskQueue
from ..repositories.audit_repository import SqlAlchemyAuditRepository
from ..repositories.document_repository import SqlAlchemyDocumentRepository
from ..repositories.relationship_repository import SqlAlchemyRelationshipRepository
from ..repositories.symbol_repository import SqlAlchemySymbolRepository
from ..repositories.user_repository import SqlAlchemyUserRepository


class SqlAlchemyUnitOfWork(UnitOfWork):
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], settings: Settings
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        self._session = self._session_factory()
        s = self._session
        self.documents = SqlAlchemyDocumentRepository(s)
        self.symbols = SqlAlchemySymbolRepository(s)
        self.relationships = SqlAlchemyRelationshipRepository(s)
        self.audit = SqlAlchemyAuditRepository(s)
        self.users = SqlAlchemyUserRepository(s)
        self.task_queue = SqlAlchemyTaskQueue(s)
        self.events = PostgresEventPublisher(
            self.task_queue, max_attempts=self._settings.task_max_retries
        )
        return self

    async def __aexit__(self, exc_type: object, *_: object) -> None:
        try:
            if exc_type is not None:
                await self.rollback()
        finally:
            assert self._session is not None
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        assert self._session is not None
        await self._session.commit()

    async def rollback(self) -> None:
        assert self._session is not None
        await self._session.rollback()
