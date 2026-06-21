"""Document use cases: upload (validate→scan→store→persist→enqueue), query, cancel, reprocess.

All mutations run inside one Unit of Work so the document row, audit entry, and first queue
task commit atomically (transactional outbox).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from ...core.config import Settings
from ...core.errors import NotFoundError, ProcessingError
from ...domain.entities import AuditLog, Document
from ...domain.enums import ProcessingStage, ProcessingStatus
from ...domain.events import DocumentUploaded
from ...domain.ports import ObjectStore, VirusScanner
from ..security import Principal
from ..unit_of_work import UnitOfWork
from .file_validation import FileValidator


@dataclass(frozen=True, slots=True)
class UploadResult:
    document: Document
    deduplicated: bool


class DocumentService:
    def __init__(
        self,
        uow: UnitOfWork,
        *,
        validator: FileValidator,
        object_store: ObjectStore,
        virus_scanner: VirusScanner,
        settings: Settings,
    ) -> None:
        self._uow = uow
        self._validator = validator
        self._store = object_store
        self._scanner = virus_scanner
        self._settings = settings

    async def upload(
        self,
        *,
        principal: Principal,
        filename: str,
        content: bytes,
        declared_mime: str,
        correlation_id: str | None = None,
    ) -> UploadResult:
        validated = self._validator.validate(
            filename=filename, content=content, declared_mime=declared_mime
        )
        # AV scan before anything is persisted/processed (fail-closed).
        await asyncio.to_thread(self._scanner.scan, content)

        async with self._uow:
            existing = await self._uow.documents.get_by_owner_and_hash(
                principal.user_id, validated.content_hash
            )
            if existing is not None:
                return UploadResult(document=existing, deduplicated=True)

            doc = Document(
                owner_id=principal.user_id,
                filename=validated.filename,
                content_hash=validated.content_hash,
                storage_uri="",  # set after we know the id
                mime_type=validated.mime_type,
                size_bytes=validated.size_bytes,
            )
            doc.storage_uri = f"raw/{principal.user_id}/{doc.id}.pdf"
            await asyncio.to_thread(
                self._store.put, doc.storage_uri, content, validated.mime_type
            )

            await self._uow.documents.add(doc)
            await self._uow.audit.add(
                AuditLog(
                    actor_id=principal.user_id,
                    entity_type="document",
                    entity_id=doc.id,
                    action="upload",
                    after={"filename": doc.filename, "size_bytes": doc.size_bytes},
                    correlation_id=correlation_id,
                )
            )
            await self._uow.events.publish(
                DocumentUploaded(aggregate_id=doc.id, correlation_id=correlation_id)
            )
            await self._uow.commit()
            return UploadResult(document=doc, deduplicated=False)

    async def get(self, principal: Principal, document_id: UUID) -> Document:
        async with self._uow:
            doc = await self._uow.documents.get(document_id)
            if doc is None:
                raise NotFoundError(f"document {document_id} not found")
            principal.require_owner_or_admin(doc.owner_id)
            return doc

    async def list(
        self,
        principal: Principal,
        *,
        status: ProcessingStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Document], int]:
        async with self._uow:
            return await self._uow.documents.list_by_owner(
                principal.user_id, status=status, limit=limit, offset=offset
            )

    async def status(self, principal: Principal, document_id: UUID) -> tuple[Document, object]:
        async with self._uow:
            doc = await self._uow.documents.get(document_id)
            if doc is None:
                raise NotFoundError(f"document {document_id} not found")
            principal.require_owner_or_admin(doc.owner_id)
            job = await self._uow.documents.get_job(document_id)
            return doc, job

    async def cancel(self, principal: Principal, document_id: UUID) -> Document:
        async with self._uow:
            doc = await self._uow.documents.get(document_id)
            if doc is None:
                raise NotFoundError(f"document {document_id} not found")
            principal.require_owner_or_admin(doc.owner_id)
            doc.cancel()
            await self._uow.documents.update(doc)
            await self._uow.audit.add(
                AuditLog(
                    actor_id=principal.user_id,
                    entity_type="document",
                    entity_id=doc.id,
                    action="cancel",
                )
            )
            await self._uow.commit()
            return doc

    async def reprocess(self, principal: Principal, document_id: UUID) -> Document:
        async with self._uow:
            doc = await self._uow.documents.get(document_id)
            if doc is None:
                raise NotFoundError(f"document {document_id} not found")
            principal.require_owner_or_admin(doc.owner_id)
            if doc.status not in (ProcessingStatus.FAILED, ProcessingStatus.COMPLETED):
                raise ProcessingError("only FAILED or COMPLETED documents can be reprocessed")
            if doc.status is ProcessingStatus.FAILED:
                doc.transition_to(ProcessingStatus.QUEUED)
            await self._uow.documents.update(doc)
            await self._uow.task_queue.enqueue(
                doc.id, ProcessingStage.VALIDATE, max_attempts=self._settings.task_max_retries
            )
            await self._uow.audit.add(
                AuditLog(
                    actor_id=principal.user_id,
                    entity_type="document",
                    entity_id=doc.id,
                    action="reprocess",
                )
            )
            await self._uow.commit()
            return doc
