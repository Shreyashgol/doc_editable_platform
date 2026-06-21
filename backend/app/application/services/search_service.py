"""Vector similarity search use cases (the foundation for AI search / RAG).

A query is one of: an existing symbol's embedding, a free-text query (cross-modal via the
embedder's text tower), or an uploaded image crop. Results are scoped to the caller's documents
unless they are admin.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from uuid import UUID

from ...core.errors import NotFoundError, ValidationError
from ...domain.entities import Symbol
from ...domain.ports import Embedder
from ..security import Principal
from ..unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class SearchHit:
    symbol: Symbol
    score: float


class SearchService:
    def __init__(self, uow: UnitOfWork, embedder: Embedder) -> None:
        self._uow = uow
        self._embedder = embedder

    async def _query_vector(
        self,
        uow: UnitOfWork,
        principal: Principal,
        *,
        symbol_id: UUID | None,
        text: str | None,
        image_b64: str | None,
    ) -> list[float]:
        provided = [v for v in (symbol_id, text, image_b64) if v is not None]
        if len(provided) != 1:
            raise ValidationError("exactly one of symbol_id, text, image_b64 is required")

        if symbol_id is not None:
            symbol = await uow.symbols.get(symbol_id)
            if symbol is None:
                raise NotFoundError(f"symbol {symbol_id} not found")
            doc = await uow.documents.get(symbol.document_id)
            if doc is None:
                raise NotFoundError("owning document not found")
            principal.require_owner_or_admin(doc.owner_id)
            if symbol.embedding is None:
                raise ValidationError("symbol has no embedding yet")
            return symbol.embedding

        if text is not None:
            return await asyncio.to_thread(self._embedder.embed_text, text)

        assert image_b64 is not None
        try:
            raw = base64.b64decode(image_b64, validate=True)
        except Exception as exc:
            raise ValidationError("image_b64 is not valid base64") from exc
        return await asyncio.to_thread(self._embedder.embed_image, raw)

    async def similar(
        self,
        principal: Principal,
        *,
        symbol_id: UUID | None = None,
        text: str | None = None,
        image_b64: str | None = None,
        top_k: int = 10,
        document_id: UUID | None = None,
        symbol_type: str | None = None,
    ) -> list[SearchHit]:
        async with self._uow:
            if document_id is not None:
                doc = await self._uow.documents.get(document_id)
                if doc is None:
                    raise NotFoundError(f"document {document_id} not found")
                principal.require_owner_or_admin(doc.owner_id)

            vector = await self._query_vector(
                self._uow, principal, symbol_id=symbol_id, text=text, image_b64=image_b64
            )
            # Admins may search globally; everyone else is scoped to their own documents.
            owner_scope = None if principal.is_admin else principal.user_id
            results = await self._uow.symbols.search_similar(
                vector,
                top_k=top_k,
                document_id=document_id,
                owner_id=owner_scope,
                symbol_type=symbol_type,
            )
            return [SearchHit(symbol=s, score=score) for s, score in results]
