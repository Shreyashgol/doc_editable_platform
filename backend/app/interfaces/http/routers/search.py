from __future__ import annotations

from fastapi import APIRouter, Depends

from ....application.security import Principal
from ....application.services.search_service import SearchService
from ..deps import get_principal, get_search_service
from ..schemas.search import SearchHitResponse, SearchRequest, SearchResponse
from ..schemas.symbols import SymbolResponse

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/similar", response_model=SearchResponse)
async def search_similar(
    body: SearchRequest,
    principal: Principal = Depends(get_principal),
    service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    hits = await service.similar(
        principal,
        symbol_id=body.symbol_id,
        text=body.text,
        image_b64=body.image_b64,
        top_k=body.top_k,
        document_id=body.document_id,
        symbol_type=body.type,
    )
    return SearchResponse(
        hits=[
            SearchHitResponse(score=h.score, symbol=SymbolResponse.from_domain(h.symbol))
            for h in hits
        ]
    )
