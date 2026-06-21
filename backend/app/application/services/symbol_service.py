"""Symbol use cases: read, versioned edit, typed properties, version history."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...core.errors import NotFoundError
from ...domain.entities import AuditLog, Symbol, SymbolProperty, SymbolVersion
from ...domain.enums import PropertyValueType, SymbolType
from ...domain.value_objects import BBox
from ..security import Principal
from ..unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class PropertyInput:
    key: str
    value_type: PropertyValueType
    value: object


class SymbolService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def _load_owned(self, uow: UnitOfWork, principal: Principal, symbol_id: UUID) -> Symbol:
        symbol = await uow.symbols.get(symbol_id)
        if symbol is None:
            raise NotFoundError(f"symbol {symbol_id} not found")
        doc = await uow.documents.get(symbol.document_id)
        if doc is None:
            raise NotFoundError("owning document not found")
        principal.require_owner_or_admin(doc.owner_id)
        return symbol

    async def get(self, principal: Principal, symbol_id: UUID) -> Symbol:
        async with self._uow:
            return await self._load_owned(self._uow, principal, symbol_id)

    async def list_by_document(
        self, principal: Principal, document_id: UUID, *, page_number: int | None = None
    ) -> list[Symbol]:
        async with self._uow:
            doc = await self._uow.documents.get(document_id)
            if doc is None:
                raise NotFoundError(f"document {document_id} not found")
            principal.require_owner_or_admin(doc.owner_id)
            return await self._uow.symbols.list_by_document(document_id, page_number=page_number)

    async def edit(
        self,
        principal: Principal,
        symbol_id: UUID,
        *,
        bbox: BBox | None = None,
        rotation: float | None = None,
        symbol_type: SymbolType | None = None,
        label: str | None = None,
        reason: str = "manual edit",
    ) -> Symbol:
        async with self._uow:
            symbol = await self._load_owned(self._uow, principal, symbol_id)
            # Snapshot current state BEFORE mutation for the immutable version history.
            prior = SymbolVersion(
                symbol_id=symbol.id,
                version=symbol.version,
                snapshot=symbol.snapshot(),
                changed_by=principal.user_id,
                change_reason=reason,
            )
            if bbox is not None:
                symbol.bbox = bbox
            if rotation is not None:
                symbol.rotation = rotation % 360.0
            if symbol_type is not None:
                symbol.symbol_type = symbol_type
            if label is not None:
                symbol.label = label
            symbol.version += 1

            await self._uow.symbols.update(symbol)
            await self._uow.symbols.add_version(prior)
            await self._uow.audit.add(
                AuditLog(
                    actor_id=principal.user_id,
                    entity_type="symbol",
                    entity_id=symbol.id,
                    action="edit",
                    before=prior.snapshot,
                    after=symbol.snapshot(),
                )
            )
            await self._uow.commit()
            return symbol

    async def upsert_properties(
        self, principal: Principal, symbol_id: UUID, properties: list[PropertyInput]
    ) -> Symbol:
        async with self._uow:
            symbol = await self._load_owned(self._uow, principal, symbol_id)
            domain_props = [
                SymbolProperty(
                    symbol_id=symbol.id, key=p.key, value_type=p.value_type, value=p.value
                )
                for p in properties
            ]
            await self._uow.symbols.upsert_properties(symbol.id, domain_props)
            await self._uow.audit.add(
                AuditLog(
                    actor_id=principal.user_id,
                    entity_type="symbol",
                    entity_id=symbol.id,
                    action="properties_upsert",
                    after={"keys": [p.key for p in properties]},
                )
            )
            await self._uow.commit()
            refreshed = await self._uow.symbols.get(symbol.id)
            assert refreshed is not None
            return refreshed

    async def list_versions(
        self, principal: Principal, symbol_id: UUID
    ) -> list[SymbolVersion]:
        async with self._uow:
            await self._load_owned(self._uow, principal, symbol_id)
            return await self._uow.symbols.list_versions(symbol_id)
