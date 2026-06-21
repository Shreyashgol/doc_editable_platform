from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from ....domain.entities import Relationship, Symbol
from ....domain.enums import RelationshipType


class GraphNode(BaseModel):
    id: UUID
    type: str
    label: str | None
    page_number: int

    @classmethod
    def from_symbol(cls, s: Symbol) -> GraphNode:
        return cls(id=s.id, type=s.symbol_type.value, label=s.label, page_number=s.page_number)


class GraphEdge(BaseModel):
    id: UUID
    source: UUID
    target: UUID
    type: str
    confidence: float

    @classmethod
    def from_relationship(cls, r: Relationship) -> GraphEdge:
        return cls(
            id=r.id,
            source=r.source_symbol_id,
            target=r.target_symbol_id,
            type=r.type.value,
            confidence=r.confidence,
        )


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class CreateEdgeRequest(BaseModel):
    document_id: UUID
    source_symbol_id: UUID
    target_symbol_id: UUID
    type: RelationshipType
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class RelationshipResponse(BaseModel):
    id: UUID
    document_id: UUID
    source: UUID
    target: UUID
    type: str
    confidence: float

    @classmethod
    def from_domain(cls, r: Relationship) -> RelationshipResponse:
        return cls(
            id=r.id,
            document_id=r.document_id,
            source=r.source_symbol_id,
            target=r.target_symbol_id,
            type=r.type.value,
            confidence=r.confidence,
        )
