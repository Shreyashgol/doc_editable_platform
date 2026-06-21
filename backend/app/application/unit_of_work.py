"""Unit of Work — a transactional boundary exposing the repositories an operation needs.

Application services do all their work inside one UoW and commit once, so a use case is atomic
(e.g. create document + enqueue first task + write audit all commit together — the outbox).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.ports import (
    AuditRepository,
    DocumentRepository,
    EventPublisher,
    RelationshipRepository,
    SymbolRepository,
    TaskQueue,
    UserRepository,
)


class UnitOfWork(ABC):
    documents: DocumentRepository
    symbols: SymbolRepository
    relationships: RelationshipRepository
    audit: AuditRepository
    users: UserRepository
    task_queue: TaskQueue
    events: EventPublisher

    @abstractmethod
    async def __aenter__(self) -> UnitOfWork: ...

    @abstractmethod
    async def __aexit__(self, *exc: object) -> None: ...

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...
