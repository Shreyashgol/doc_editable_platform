from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status

from ....application.security import Principal
from ....application.services.document_service import DocumentService
from ....core.config import get_settings
from ....core.errors import FileValidationError
from ....domain.enums import ProcessingStatus
from ..deps import get_document_service, get_principal
from ..schemas.common import Page
from ..schemas.documents import (
    DocumentResponse,
    DocumentStatusResponse,
    UploadResponse,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    principal: Principal = Depends(get_principal),
    service: DocumentService = Depends(get_document_service),
) -> UploadResponse:
    content = await file.read()
    # Guard memory before doing anything else with the bytes.
    if len(content) > get_settings().max_upload_bytes:
        raise FileValidationError("file exceeds maximum size")
    result = await service.upload(
        principal=principal,
        filename=file.filename or "upload.pdf",
        content=content,
        declared_mime=file.content_type or "application/octet-stream",
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    doc = result.document
    prefix = get_settings().api_v1_prefix
    return UploadResponse(
        id=doc.id,
        status=doc.status.value,
        deduplicated=result.deduplicated,
        status_url=f"{prefix}/documents/{doc.id}/status",
    )


@router.get("", response_model=Page[DocumentResponse])
async def list_documents(
    principal: Principal = Depends(get_principal),
    service: DocumentService = Depends(get_document_service),
    status_filter: ProcessingStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[DocumentResponse]:
    docs, total = await service.list(principal, status=status_filter, limit=limit, offset=offset)
    return Page(
        items=[DocumentResponse.from_domain(d) for d in docs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    principal: Principal = Depends(get_principal),
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    return DocumentResponse.from_domain(await service.get(principal, document_id))


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def document_status(
    document_id: UUID,
    principal: Principal = Depends(get_principal),
    service: DocumentService = Depends(get_document_service),
) -> DocumentStatusResponse:
    doc, job = await service.status(principal, document_id)
    return DocumentStatusResponse.from_domain(doc, job)


@router.post("/{document_id}/cancel", response_model=DocumentResponse)
async def cancel_document(
    document_id: UUID,
    principal: Principal = Depends(get_principal),
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    return DocumentResponse.from_domain(await service.cancel(principal, document_id))


@router.post("/{document_id}/reprocess", response_model=DocumentResponse)
async def reprocess_document(
    document_id: UUID,
    principal: Principal = Depends(get_principal),
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    return DocumentResponse.from_domain(await service.reprocess(principal, document_id))
