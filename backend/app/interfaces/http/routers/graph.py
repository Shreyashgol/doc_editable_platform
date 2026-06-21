from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status

from ....application.security import Principal
from ....application.services.graph_service import GraphService
from ..deps import get_graph_service, get_principal
from ..schemas.graph import (
    CreateEdgeRequest,
    GraphEdge,
    GraphNode,
    GraphResponse,
    RelationshipResponse,
)

documents_router = APIRouter(prefix="/documents", tags=["graph"])
router = APIRouter(prefix="/relationships", tags=["graph"])


@documents_router.get("/{document_id}/graph", response_model=GraphResponse)
async def get_graph(
    document_id: UUID,
    principal: Principal = Depends(get_principal),
    service: GraphService = Depends(get_graph_service),
) -> GraphResponse:
    symbols, edges = await service.get_graph(principal, document_id)
    return GraphResponse(
        nodes=[GraphNode.from_symbol(s) for s in symbols],
        edges=[GraphEdge.from_relationship(e) for e in edges],
    )


@router.post("", response_model=RelationshipResponse, status_code=status.HTTP_201_CREATED)
async def create_edge(
    body: CreateEdgeRequest,
    principal: Principal = Depends(get_principal),
    service: GraphService = Depends(get_graph_service),
) -> RelationshipResponse:
    edge = await service.add_edge(
        principal,
        document_id=body.document_id,
        source_symbol_id=body.source_symbol_id,
        target_symbol_id=body.target_symbol_id,
        relationship_type=body.type,
        confidence=body.confidence,
    )
    return RelationshipResponse.from_domain(edge)


@router.delete("/{relationship_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_edge(
    relationship_id: UUID,
    principal: Principal = Depends(get_principal),
    service: GraphService = Depends(get_graph_service),
) -> None:
    await service.delete_edge(principal, relationship_id)
