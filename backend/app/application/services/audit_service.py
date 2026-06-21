"""Audit query use case (admin-only)."""

from __future__ import annotations

from uuid import UUID

from ...domain.entities import AuditLog
from ...domain.enums import Role
from ..security import Principal
from ..unit_of_work import UnitOfWork


class AuditService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def query(
        self,
        principal: Principal,
        *,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        actor_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        principal.require_role(Role.ADMIN)
        async with self._uow:
            return await self._uow.audit.query(
                entity_type=entity_type,
                entity_id=entity_id,
                actor_id=actor_id,
                limit=limit,
                offset=offset,
            )
