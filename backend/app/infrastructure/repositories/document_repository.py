from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...domain.entities import Document, Page, ProcessingJob
from ...domain.enums import ProcessingStatus
from ...domain.ports import DocumentRepository
from ..db import mappers
from ..db.models import DocumentModel, PageModel, ProcessingJobModel


class SqlAlchemyDocumentRepository(DocumentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, document: Document) -> Document:
        row = mappers.document_to_row(document)
        self._session.add(row)
        await self._session.flush()
        return document

    async def get(self, document_id: UUID) -> Document | None:
        row = await self._session.get(DocumentModel, document_id)
        return mappers.document_to_domain(row) if row else None

    async def get_by_owner_and_hash(
        self, owner_id: UUID, content_hash: str
    ) -> Document | None:
        stmt = select(DocumentModel).where(
            DocumentModel.owner_id == owner_id,
            DocumentModel.content_hash == content_hash,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.document_to_domain(row) if row else None

    async def update(self, document: Document) -> None:
        row = await self._session.get(DocumentModel, document.id)
        if row is None:
            raise ValueError(f"Document {document.id} not found for update")
        mappers.document_apply_to_row(document, row)
        await self._session.flush()

    async def list_by_owner(
        self,
        owner_id: UUID,
        *,
        status: ProcessingStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Document], int]:
        conditions = [DocumentModel.owner_id == owner_id]
        if status is not None:
            conditions.append(DocumentModel.status == status.value)
        total = (
            await self._session.execute(
                select(func.count()).select_from(DocumentModel).where(*conditions)
            )
        ).scalar_one()
        stmt = (
            select(DocumentModel)
            .where(*conditions)
            .order_by(DocumentModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.document_to_domain(r) for r in rows], total

    async def add_pages(self, pages: list[Page]) -> None:
        self._session.add_all([mappers.page_to_row(p) for p in pages])
        await self._session.flush()

    async def list_pages(self, document_id: UUID) -> list[Page]:
        stmt = (
            select(PageModel)
            .where(PageModel.document_id == document_id)
            .order_by(PageModel.page_number)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            Page(
                id=r.id,
                document_id=r.document_id,
                page_number=r.page_number,
                width_px=r.width_px,
                height_px=r.height_px,
                dpi=r.dpi,
                render_uri=r.render_uri,
                created_at=r.created_at,
            )
            for r in rows
        ]

    async def delete_pages(self, document_id: UUID) -> None:
        await self._session.execute(
            delete(PageModel).where(PageModel.document_id == document_id)
        )
        await self._session.flush()

    async def get_job(self, document_id: UUID) -> ProcessingJob | None:
        stmt = select(ProcessingJobModel).where(ProcessingJobModel.document_id == document_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.job_to_domain(row) if row else None

    async def upsert_job(self, job: ProcessingJob) -> None:
        stmt = select(ProcessingJobModel).where(ProcessingJobModel.document_id == job.document_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            self._session.add(mappers.job_to_row(job))
        else:
            mappers.job_apply_to_row(job, row)
        await self._session.flush()

    async def get_with_pages(self, document_id: UUID) -> Document | None:
        stmt = (
            select(DocumentModel)
            .where(DocumentModel.id == document_id)
            .options(selectinload(DocumentModel.pages))
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.document_to_domain(row) if row else None
