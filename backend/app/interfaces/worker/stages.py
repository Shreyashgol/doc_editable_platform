"""Pipeline stage handlers.

Each handler advances one document through one stage inside the runner's Unit of Work, then
enqueues the next stage's task in the same transaction (atomic stage completion). Handlers are
idempotent: re-running ``pdf_extract`` rebuilds pages/symbols from a clean slate, and the
later stages update-in-place, so a retry never duplicates data.

State transitions are conditional on the current state, so retries and the reprocess path
(which may re-enter mid-pipeline) never trip the state machine.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from ...application.unit_of_work import UnitOfWork
from ...core.errors import ProcessingError
from ...domain.entities import AuditLog, Page, ProcessingJob, Symbol
from ...domain.enums import ProcessingStage, ProcessingStatus
from ...domain.services import associate_text_to_symbol
from ...domain.value_objects import BBox
from .engines import WorkerEngines

# Returns True if the chain should continue (next stage enqueued), False if it stopped
# (e.g. the document was cancelled).
StageHandler = Callable[[UnitOfWork, WorkerEngines, "object"], Awaitable[bool]]


async def _load_job(uow: UnitOfWork, document_id) -> ProcessingJob:
    job = await uow.documents.get_job(document_id)
    if job is None:
        job = ProcessingJob(document_id=document_id)
    return job


def _max_attempts(engines: WorkerEngines) -> int:
    return engines.settings.task_max_retries


async def _get_active_document(uow: UnitOfWork, document_id):
    doc = await uow.documents.get(document_id)
    if doc is None:
        raise ProcessingError(f"document {document_id} no longer exists")
    return doc


async def handle_validate(uow: UnitOfWork, engines: WorkerEngines, task) -> bool:
    doc = await _get_active_document(uow, task.document_id)
    if doc.status is ProcessingStatus.CANCELLED:
        return False
    job = await _load_job(uow, doc.id)
    job.record_attempt(ProcessingStage.VALIDATE)

    if doc.status is ProcessingStatus.UPLOADED:
        doc.transition_to(ProcessingStatus.VALIDATING)

    raw = await asyncio.to_thread(engines.object_store.get, doc.storage_uri)
    await asyncio.to_thread(
        engines.parser.validate_safety,
        raw,
        max_pages=engines.settings.max_pdf_pages,
        max_page_pixels=engines.settings.max_page_pixels,
    )
    doc.page_count = await asyncio.to_thread(engines.parser.page_count, raw)

    if doc.status is ProcessingStatus.VALIDATING:
        doc.transition_to(ProcessingStatus.QUEUED)
    job.succeed(0.0)
    await uow.documents.update(doc)
    await uow.documents.upsert_job(job)
    await uow.task_queue.enqueue(
        doc.id, ProcessingStage.PDF_EXTRACT, max_attempts=_max_attempts(engines)
    )
    return True


async def handle_pdf_extract(uow: UnitOfWork, engines: WorkerEngines, task) -> bool:
    doc = await _get_active_document(uow, task.document_id)
    if doc.status is ProcessingStatus.CANCELLED:
        return False
    job = await _load_job(uow, doc.id)
    job.record_attempt(ProcessingStage.PDF_EXTRACT)
    if doc.status is ProcessingStatus.QUEUED:
        doc.transition_to(ProcessingStatus.PROCESSING)

    # Idempotent rebuild.
    await uow.relationships.delete_by_document(doc.id)
    await uow.symbols.delete_by_document(doc.id)
    await uow.documents.delete_pages(doc.id)

    raw = await asyncio.to_thread(engines.object_store.get, doc.storage_uri)
    rendered = await asyncio.to_thread(
        engines.parser.render_pages, raw, engines.settings.render_dpi
    )

    pages: list[Page] = []
    symbols: list[Symbol] = []
    for page_number, png, width, height in rendered:
        render_key = f"renders/{doc.id}/page-{page_number}.png"
        await asyncio.to_thread(engines.object_store.put, render_key, png, "image/png")
        pages.append(
            Page(
                document_id=doc.id,
                page_number=page_number,
                width_px=width,
                height_px=height,
                dpi=engines.settings.render_dpi,
                render_uri=render_key,
            )
        )
        detections = await asyncio.to_thread(engines.extractor.extract, png, page_number)
        for bbox, crop in detections:
            symbol = Symbol(
                document_id=doc.id,
                page_number=page_number,
                bbox=bbox,
                crop_uri="",  # set after id is known
            )
            symbol.crop_uri = f"crops/{doc.id}/page-{page_number}/{symbol.id}.png"
            await asyncio.to_thread(engines.object_store.put, symbol.crop_uri, crop, "image/png")
            symbols.append(symbol)

    await uow.documents.add_pages(pages)
    if symbols:
        await uow.symbols.add_many(symbols)
    job.succeed(0.0)
    await uow.documents.update(doc)
    await uow.documents.upsert_job(job)
    await uow.task_queue.enqueue(doc.id, ProcessingStage.OCR, max_attempts=_max_attempts(engines))
    return True


async def handle_ocr(uow: UnitOfWork, engines: WorkerEngines, task) -> bool:
    doc = await _get_active_document(uow, task.document_id)
    if doc.status is ProcessingStatus.CANCELLED:
        return False
    job = await _load_job(uow, doc.id)
    job.record_attempt(ProcessingStage.OCR)
    if doc.status is ProcessingStatus.PROCESSING:
        doc.transition_to(ProcessingStatus.OCR_RUNNING)

    pages = await uow.documents.list_pages(doc.id)
    symbols = await uow.symbols.list_by_document(doc.id)
    by_page: dict[int, list[Symbol]] = {}
    for s in symbols:
        by_page.setdefault(s.page_number, []).append(s)

    for page in pages:
        page_symbols = by_page.get(page.page_number, [])
        if not page_symbols:
            continue
        render = await asyncio.to_thread(engines.object_store.get, page.render_uri)
        tokens = await asyncio.to_thread(engines.ocr.extract_text, render)
        associations = associate_text_to_symbol(
            page_symbols,
            tokens,
            max_distance=engines.settings.label_association_max_distance,
        )
        for symbol in page_symbols:
            token = associations.get(symbol.id)
            if token is not None:
                symbol.assign_label(token.text)
                await uow.symbols.update(symbol)

    job.succeed(0.0)
    await uow.documents.update(doc)
    await uow.documents.upsert_job(job)
    await uow.task_queue.enqueue(
        doc.id, ProcessingStage.CLASSIFY, max_attempts=_max_attempts(engines)
    )
    return True


async def handle_classify(uow: UnitOfWork, engines: WorkerEngines, task) -> bool:
    doc = await _get_active_document(uow, task.document_id)
    if doc.status is ProcessingStatus.CANCELLED:
        return False
    job = await _load_job(uow, doc.id)
    job.record_attempt(ProcessingStage.CLASSIFY)
    if doc.status is ProcessingStatus.OCR_RUNNING:
        doc.transition_to(ProcessingStatus.CLASSIFYING)

    for symbol in await uow.symbols.list_by_document(doc.id):
        classification = engines.classifier.classify(label=symbol.label, crop_png=None)
        symbol.apply_classification(classification)
        await uow.symbols.update(symbol)

    job.succeed(0.0)
    await uow.documents.update(doc)
    await uow.documents.upsert_job(job)
    await uow.task_queue.enqueue(doc.id, ProcessingStage.EMBED, max_attempts=_max_attempts(engines))
    return True


async def handle_embed(uow: UnitOfWork, engines: WorkerEngines, task) -> bool:
    doc = await _get_active_document(uow, task.document_id)
    if doc.status is ProcessingStatus.CANCELLED:
        return False
    job = await _load_job(uow, doc.id)
    job.record_attempt(ProcessingStage.EMBED)
    if doc.status is ProcessingStatus.CLASSIFYING:
        doc.transition_to(ProcessingStatus.EMBEDDING)

    for symbol in await uow.symbols.list_by_document(doc.id):
        crop = await asyncio.to_thread(engines.object_store.get, symbol.crop_uri)
        vector = await asyncio.to_thread(engines.embedder.embed_image, crop)
        await uow.symbols.set_embedding(symbol.id, engines.embedder.model_name, vector)

    job.succeed(0.0)
    await uow.documents.update(doc)
    await uow.documents.upsert_job(job)
    await uow.task_queue.enqueue(doc.id, ProcessingStage.GRAPH, max_attempts=_max_attempts(engines))
    return True


async def handle_graph(uow: UnitOfWork, engines: WorkerEngines, task) -> bool:
    doc = await _get_active_document(uow, task.document_id)
    if doc.status is ProcessingStatus.CANCELLED:
        return False
    job = await _load_job(uow, doc.id)
    job.record_attempt(ProcessingStage.GRAPH)

    await uow.relationships.delete_by_document(doc.id)
    symbols = await uow.symbols.list_by_document(doc.id)
    edges = engines.inferrer.infer(symbols)
    if edges:
        await uow.relationships.add_many(edges)

    job.succeed(0.0)
    await uow.documents.upsert_job(job)
    await uow.task_queue.enqueue(
        doc.id, ProcessingStage.FINALIZE, max_attempts=_max_attempts(engines)
    )
    return True


async def handle_finalize(uow: UnitOfWork, engines: WorkerEngines, task) -> bool:
    doc = await _get_active_document(uow, task.document_id)
    if doc.status is ProcessingStatus.CANCELLED:
        return False
    job = await _load_job(uow, doc.id)
    job.record_attempt(ProcessingStage.FINALIZE)
    if doc.status is ProcessingStatus.EMBEDDING:
        doc.transition_to(ProcessingStatus.COMPLETED)
    job.succeed(0.0)
    await uow.documents.update(doc)
    await uow.documents.upsert_job(job)
    await uow.audit.add(
        AuditLog(actor_id=None, entity_type="document", entity_id=doc.id, action="completed")
    )
    return True


STAGE_HANDLERS: dict[ProcessingStage, StageHandler] = {
    ProcessingStage.VALIDATE: handle_validate,
    ProcessingStage.PDF_EXTRACT: handle_pdf_extract,
    ProcessingStage.OCR: handle_ocr,
    ProcessingStage.CLASSIFY: handle_classify,
    ProcessingStage.EMBED: handle_embed,
    ProcessingStage.GRAPH: handle_graph,
    ProcessingStage.FINALIZE: handle_finalize,
}

# Re-exported for tests that build candidate boxes.
__all__ = ["STAGE_HANDLERS", "BBox"]
