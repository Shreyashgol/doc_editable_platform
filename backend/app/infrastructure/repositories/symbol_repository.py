from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...domain.entities import Symbol, SymbolProperty, SymbolVersion
from ...domain.ports import SymbolRepository
from ..db import mappers
from ..db.models import (
    DocumentModel,
    EmbeddingModel,
    SymbolModel,
    SymbolPropertyModel,
    SymbolVersionModel,
)


class SqlAlchemySymbolRepository(SymbolRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(self, symbols: list[Symbol]) -> None:
        self._session.add_all([mappers.symbol_to_row(s) for s in symbols])
        await self._session.flush()

    async def delete_by_document(self, document_id: UUID) -> None:
        await self._session.execute(
            delete(SymbolModel).where(SymbolModel.document_id == document_id)
        )
        await self._session.flush()

    async def get(self, symbol_id: UUID) -> Symbol | None:
        stmt = (
            select(SymbolModel)
            .where(SymbolModel.id == symbol_id)
            .options(selectinload(SymbolModel.properties), selectinload(SymbolModel.embedding))
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.symbol_to_domain(row) if row else None

    async def list_by_document(
        self, document_id: UUID, *, page_number: int | None = None
    ) -> list[Symbol]:
        conditions = [SymbolModel.document_id == document_id]
        if page_number is not None:
            conditions.append(SymbolModel.page_number == page_number)
        stmt = (
            select(SymbolModel)
            .where(*conditions)
            .options(selectinload(SymbolModel.properties), selectinload(SymbolModel.embedding))
            .order_by(SymbolModel.page_number, SymbolModel.created_at)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.symbol_to_domain(r) for r in rows]

    async def update(self, symbol: Symbol) -> None:
        row = await self._session.get(SymbolModel, symbol.id)
        if row is None:
            raise ValueError(f"Symbol {symbol.id} not found for update")
        mappers.symbol_apply_to_row(symbol, row)
        await self._session.flush()

    async def add_version(self, version: SymbolVersion) -> None:
        self._session.add(mappers.version_to_row(version))
        await self._session.flush()

    async def list_versions(self, symbol_id: UUID) -> list[SymbolVersion]:
        stmt = (
            select(SymbolVersionModel)
            .where(SymbolVersionModel.symbol_id == symbol_id)
            .order_by(SymbolVersionModel.version.desc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.version_to_domain(r) for r in rows]

    async def upsert_properties(self, symbol_id: UUID, properties: list[SymbolProperty]) -> None:
        # Replace-set semantics keyed by symbol; simple and predictable for the editor.
        await self._session.execute(
            delete(SymbolPropertyModel).where(SymbolPropertyModel.symbol_id == symbol_id)
        )
        for p in properties:
            self._session.add(
                SymbolPropertyModel(
                    id=p.id,
                    symbol_id=symbol_id,
                    key=p.key,
                    value_type=p.value_type.value,
                    value={"v": p.value},
                )
            )
        await self._session.flush()

    async def set_embedding(self, symbol_id: UUID, model: str, vector: list[float]) -> None:
        existing = (
            await self._session.execute(
                select(EmbeddingModel).where(EmbeddingModel.symbol_id == symbol_id)
            )
        ).scalar_one_or_none()
        if existing is None:
            self._session.add(
                EmbeddingModel(symbol_id=symbol_id, model=model, dim=len(vector), embedding=vector)
            )
        else:
            existing.model = model
            existing.dim = len(vector)
            existing.embedding = vector
        await self._session.flush()

    async def search_similar(
        self,
        vector: list[float],
        *,
        top_k: int = 10,
        document_id: UUID | None = None,
        owner_id: UUID | None = None,
        symbol_type: str | None = None,
    ) -> list[tuple[Symbol, float]]:
        distance = EmbeddingModel.embedding.cosine_distance(vector).label("distance")
        stmt = (
            select(SymbolModel, distance)
            .join(EmbeddingModel, EmbeddingModel.symbol_id == SymbolModel.id)
            .options(selectinload(SymbolModel.properties), selectinload(SymbolModel.embedding))
        )
        if document_id is not None:
            stmt = stmt.where(SymbolModel.document_id == document_id)
        if owner_id is not None:
            stmt = stmt.join(DocumentModel, DocumentModel.id == SymbolModel.document_id).where(
                DocumentModel.owner_id == owner_id
            )
        if symbol_type is not None:
            stmt = stmt.where(SymbolModel.type == symbol_type)
        stmt = stmt.order_by(distance).limit(top_k)
        results = (await self._session.execute(stmt)).all()
        # cosine_distance in [0, 2]; similarity = 1 - distance (cosine similarity).
        return [(mappers.symbol_to_domain(row), 1.0 - float(dist)) for row, dist in results]
