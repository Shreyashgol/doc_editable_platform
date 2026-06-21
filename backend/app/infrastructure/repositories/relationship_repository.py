from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.entities import Relationship
from ...domain.ports import RelationshipRepository
from ..db import mappers
from ..db.models import RelationshipModel


class SqlAlchemyRelationshipRepository(RelationshipRepository):
    """Adjacency-list graph over Postgres. ``neighbours`` uses a recursive CTE so traversal
    stays in the database; the public method shape matches a future Neo4j adapter (ADR 0002)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, relationship: Relationship) -> Relationship:
        self._session.add(mappers.relationship_to_row(relationship))
        await self._session.flush()
        return relationship

    async def add_many(self, relationships: list[Relationship]) -> None:
        self._session.add_all([mappers.relationship_to_row(r) for r in relationships])
        await self._session.flush()

    async def delete(self, relationship_id: UUID) -> None:
        await self._session.execute(
            delete(RelationshipModel).where(RelationshipModel.id == relationship_id)
        )
        await self._session.flush()

    async def delete_by_document(self, document_id: UUID) -> None:
        await self._session.execute(
            delete(RelationshipModel).where(RelationshipModel.document_id == document_id)
        )
        await self._session.flush()

    async def get(self, relationship_id: UUID) -> Relationship | None:
        row = await self._session.get(RelationshipModel, relationship_id)
        return mappers.relationship_to_domain(row) if row else None

    async def list_by_document(self, document_id: UUID) -> list[Relationship]:
        stmt = select(RelationshipModel).where(RelationshipModel.document_id == document_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.relationship_to_domain(r) for r in rows]

    async def neighbours(self, symbol_id: UUID, *, depth: int = 1) -> list[Relationship]:
        if depth <= 1:
            stmt = select(RelationshipModel).where(
                or_(
                    RelationshipModel.source_symbol_id == symbol_id,
                    RelationshipModel.target_symbol_id == symbol_id,
                )
            )
            rows = (await self._session.execute(stmt)).scalars().all()
            return [mappers.relationship_to_domain(r) for r in rows]

        # Recursive CTE traversal up to `depth` hops in either direction.
        cte = text(
            """
            WITH RECURSIVE reachable(node, lvl) AS (
                SELECT CAST(:start AS uuid), 0
                UNION
                SELECT CASE WHEN r.source_symbol_id = reachable.node
                            THEN r.target_symbol_id ELSE r.source_symbol_id END,
                       reachable.lvl + 1
                FROM relationships r
                JOIN reachable
                  ON (r.source_symbol_id = reachable.node OR r.target_symbol_id = reachable.node)
                WHERE reachable.lvl < :depth
            )
            SELECT DISTINCT r.id FROM relationships r
            JOIN reachable n1 ON r.source_symbol_id = n1.node
            JOIN reachable n2 ON r.target_symbol_id = n2.node
            """
        )
        ids = (
            (await self._session.execute(cte, {"start": str(symbol_id), "depth": depth}))
            .scalars()
            .all()
        )
        if not ids:
            return []
        rows = (
            await self._session.execute(
                select(RelationshipModel).where(RelationshipModel.id.in_(ids))
            )
        ).scalars().all()
        return [mappers.relationship_to_domain(r) for r in rows]
