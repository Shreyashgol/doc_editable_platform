from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from ....application.security import Principal
from ....application.services.symbol_service import PropertyInput, SymbolService
from ....domain.value_objects import BBox
from ..deps import get_principal, get_symbol_service
from ..schemas.symbols import (
    EditSymbolRequest,
    SymbolResponse,
    SymbolVersionResponse,
    UpsertPropertiesRequest,
)

# Mounted at /documents for the list-by-document route, and /symbols for item routes.
documents_router = APIRouter(prefix="/documents", tags=["symbols"])
router = APIRouter(prefix="/symbols", tags=["symbols"])


@documents_router.get("/{document_id}/symbols", response_model=list[SymbolResponse])
async def list_symbols(
    document_id: UUID,
    principal: Principal = Depends(get_principal),
    service: SymbolService = Depends(get_symbol_service),
    page: int | None = Query(default=None, ge=1),
) -> list[SymbolResponse]:
    symbols = await service.list_by_document(principal, document_id, page_number=page)
    return [SymbolResponse.from_domain(s) for s in symbols]


@router.get("/{symbol_id}", response_model=SymbolResponse)
async def get_symbol(
    symbol_id: UUID,
    principal: Principal = Depends(get_principal),
    service: SymbolService = Depends(get_symbol_service),
) -> SymbolResponse:
    return SymbolResponse.from_domain(await service.get(principal, symbol_id))


@router.patch("/{symbol_id}", response_model=SymbolResponse)
async def edit_symbol(
    symbol_id: UUID,
    body: EditSymbolRequest,
    principal: Principal = Depends(get_principal),
    service: SymbolService = Depends(get_symbol_service),
) -> SymbolResponse:
    bbox = BBox(**body.bbox.model_dump()) if body.bbox else None
    symbol = await service.edit(
        principal,
        symbol_id,
        bbox=bbox,
        rotation=body.rotation,
        symbol_type=body.type,
        label=body.label,
        reason=body.reason,
    )
    return SymbolResponse.from_domain(symbol)


@router.get("/{symbol_id}/versions", response_model=list[SymbolVersionResponse])
async def list_symbol_versions(
    symbol_id: UUID,
    principal: Principal = Depends(get_principal),
    service: SymbolService = Depends(get_symbol_service),
) -> list[SymbolVersionResponse]:
    versions = await service.list_versions(principal, symbol_id)
    return [SymbolVersionResponse.from_domain(v) for v in versions]


@router.put("/{symbol_id}/properties", response_model=SymbolResponse)
async def upsert_properties(
    symbol_id: UUID,
    body: UpsertPropertiesRequest,
    principal: Principal = Depends(get_principal),
    service: SymbolService = Depends(get_symbol_service),
) -> SymbolResponse:
    props = [
        PropertyInput(key=p.key, value_type=p.value_type, value=p.value) for p in body.properties
    ]
    return SymbolResponse.from_domain(await service.upsert_properties(principal, symbol_id, props))
