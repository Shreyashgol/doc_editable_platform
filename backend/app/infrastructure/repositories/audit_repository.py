from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.entities import AuditLog
from ...domain.ports import AuditRepository
from ..db import mappers
from ..db.models import AuditLogModel


class SqlAlchemyAuditRepository(AuditRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: AuditLog) -> None:
        self._session.add(mappers.audit_to_row(entry))
        await self._session.flush()

    async def query(
        self,
        *,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        actor_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        conditions = []
        if entity_type is not None:
            conditions.append(AuditLogModel.entity_type == entity_type)
        if entity_id is not None:
            conditions.append(AuditLogModel.entity_id == entity_id)
        if actor_id is not None:
            conditions.append(AuditLogModel.actor_id == actor_id)
        stmt = (
            select(AuditLogModel)
            .where(*conditions)
            .order_by(AuditLogModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.audit_to_domain(r) for r in rows]
