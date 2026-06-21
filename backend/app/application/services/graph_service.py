"""Symbol-graph use cases: read the graph, create/delete edges."""

from __future__ import annotations

from uuid import UUID

from ...core.errors import NotFoundError, ValidationError
from ...domain.entities import AuditLog, Relationship, Symbol
from ...domain.enums import RelationshipType
from ..security import Principal
from ..unit_of_work import UnitOfWork


class GraphService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def get_graph(
        self, principal: Principal, document_id: UUID
    ) -> tuple[list[Symbol], list[Relationship]]:
        async with self._uow:
            doc = await self._uow.documents.get(document_id)
            if doc is None:
                raise NotFoundError(f"document {document_id} not found")
            principal.require_owner_or_admin(doc.owner_id)
            symbols = await self._uow.symbols.list_by_document(document_id)
            edges = await self._uow.relationships.list_by_document(document_id)
            return symbols, edges

    async def add_edge(
        self,
        principal: Principal,
        *,
        document_id: UUID,
        source_symbol_id: UUID,
        target_symbol_id: UUID,
        relationship_type: RelationshipType,
        confidence: float = 1.0,
    ) -> Relationship:
        if source_symbol_id == target_symbol_id:
            raise ValidationError("source and target must differ")
        async with self._uow:
            doc = await self._uow.documents.get(document_id)
            if doc is None:
                raise NotFoundError(f"document {document_id} not found")
            principal.require_owner_or_admin(doc.owner_id)
            # Both endpoints must belong to this document.
            for sid in (source_symbol_id, target_symbol_id):
                sym = await self._uow.symbols.get(sid)
                if sym is None or sym.document_id != document_id:
                    raise ValidationError(f"symbol {sid} is not part of document {document_id}")
            edge = Relationship(
                document_id=document_id,
                source_symbol_id=source_symbol_id,
                target_symbol_id=target_symbol_id,
                type=relationship_type,
                confidence=confidence,
            )
            await self._uow.relationships.add(edge)
            await self._uow.audit.add(
                AuditLog(
                    actor_id=principal.user_id,
                    entity_type="relationship",
                    entity_id=edge.id,
                    action="create",
                    after={"type": relationship_type.value},
                )
            )
            await self._uow.commit()
            return edge

    async def delete_edge(self, principal: Principal, relationship_id: UUID) -> None:
        async with self._uow:
            edge = await self._uow.relationships.get(relationship_id)
            if edge is None:
                raise NotFoundError(f"relationship {relationship_id} not found")
            doc = await self._uow.documents.get(edge.document_id)
            if doc is None:
                raise NotFoundError("owning document not found")
            principal.require_owner_or_admin(doc.owner_id)
            await self._uow.relationships.delete(relationship_id)
            await self._uow.audit.add(
                AuditLog(
                    actor_id=principal.user_id,
                    entity_type="relationship",
                    entity_id=relationship_id,
                    action="delete",
                )
            )
            await self._uow.commit()
