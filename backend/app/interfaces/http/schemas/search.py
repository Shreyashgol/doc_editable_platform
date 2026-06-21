from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from .symbols import SymbolResponse


class SearchRequest(BaseModel):
    symbol_id: UUID | None = None
    text: str | None = None
    image_b64: str | None = None
    top_k: int = Field(default=10, ge=1, le=100)
    document_id: UUID | None = None
    type: str | None = None

    @model_validator(mode="after")
    def _exactly_one_query(self) -> SearchRequest:
        provided = [v for v in (self.symbol_id, self.text, self.image_b64) if v is not None]
        if len(provided) != 1:
            raise ValueError("provide exactly one of: symbol_id, text, image_b64")
        return self


class SearchHitResponse(BaseModel):
    score: float
    symbol: SymbolResponse


class SearchResponse(BaseModel):
    hits: list[SearchHitResponse]
