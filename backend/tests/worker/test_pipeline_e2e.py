"""End-to-end worker pipeline tests.

Real PyMuPDF rendering + OpenCV extraction + Hash embeddings against the live Neon DB and the
Postgres queue. A deterministic labelling OCR fake stands in for PaddleOCR so we can assert the
full chain: detect -> OCR-associate -> classify -> embed -> graph -> COMPLETED.
"""

from __future__ import annotations

import hashlib
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.config import get_settings
from app.domain.entities import Document
from app.domain.enums import ProcessingStage, ProcessingStatus, SymbolType
from app.domain.ports import OcrEngine
from app.domain.value_objects import OcrToken
from app.infrastructure.cv.symbol_extractor import OpenCvSymbolExtractor
from app.infrastructure.db.base import create_engine_and_sessionmaker
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.storage.s3 import InMemoryObjectStore
from app.interfaces.worker.engines import build_engines
from app.interfaces.worker.runner import PipelineRunner
from sqlalchemy import text

_HAS_DB = bool(os.getenv("APP_DATABASE_URL"))
pytestmark = [
    pytest.mark.worker,
    pytest.mark.e2e,
    pytest.mark.skipif(not _HAS_DB, reason="APP_DATABASE_URL not configured"),
]

_LABELS = ["XV-100", "P-101", "PT-200", "PIC-300", "HEX-400", "T-500"]


class FakeLabelingOcrEngine(OcrEngine):
    """Returns one labelled token per detected region (token sits on the symbol centroid),
    so OCR->symbol association is deterministic without a real OCR model."""

    def __init__(self) -> None:
        self._extractor = OpenCvSymbolExtractor()

    def extract_text(self, page_png: bytes) -> list[OcrToken]:
        boxes = self._extractor.extract(page_png, 0)
        tokens: list[OcrToken] = []
        for i, (bbox, _crop) in enumerate(boxes):
            tokens.append(OcrToken(text=_LABELS[i % len(_LABELS)], bbox=bbox, confidence=0.95))
        return tokens


def _make_pid_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=600, height=400)
    for x, y in [(50, 50), (320, 60), (120, 250), (430, 260)]:
        rect = fitz.Rect(x, y, x + 60, y + 60)
        page.draw_rect(rect, color=(0, 0, 0), fill=(0, 0, 0))
    return doc.tobytes()


@pytest_asyncio.fixture
async def db():
    settings = get_settings()
    engine, sf = create_engine_and_sessionmaker(settings)
    yield settings, sf
    await engine.dispose()


async def _cleanup(sf, doc_id) -> None:
    async with sf() as s:
        await s.execute(text("DELETE FROM documents WHERE id = :d"), {"d": str(doc_id)})
        await s.commit()


async def test_full_pipeline_to_completion(db):
    settings, sf = db
    store = InMemoryObjectStore()
    pdf = _make_pid_pdf()
    owner = uuid4()

    doc = Document(
        owner_id=owner,
        filename="pid.pdf",
        content_hash=hashlib.sha256(pdf).hexdigest(),
        storage_uri="",
        mime_type="application/pdf",
        size_bytes=len(pdf),
    )
    doc.storage_uri = f"raw/{owner}/{doc.id}.pdf"
    store.put(doc.storage_uri, pdf, "application/pdf")

    uow = SqlAlchemyUnitOfWork(sf, settings)
    async with uow:
        await uow.documents.add(doc)
        await uow.task_queue.enqueue(doc.id, ProcessingStage.VALIDATE, max_attempts=3)
        await uow.commit()

    engines = build_engines(settings, object_store=store)
    engines.ocr = FakeLabelingOcrEngine()
    runner = PipelineRunner(sf, settings, engines)
    try:
        await runner.drain(max_iterations=50)

        verify = SqlAlchemyUnitOfWork(sf, settings)
        async with verify:
            d = await verify.documents.get(doc.id)
            assert d.status is ProcessingStatus.COMPLETED, d.status
            assert d.page_count == 1

            symbols = await verify.symbols.list_by_document(doc.id)
            assert len(symbols) >= 3  # the four drawn squares (allowing for merges)
            # every symbol got an embedding (full vector path exercised)
            assert all(s.embedding is not None and len(s.embedding) == 512 for s in symbols)
            # OCR association + rule classification produced known types
            types = {s.symbol_type for s in symbols}
            assert types & {SymbolType.VALVE, SymbolType.PUMP, SymbolType.PRESSURE_TRANSMITTER}
            assert all(s.label is not None for s in symbols)

            # graph edges inferred from classified symbols
            edges = await verify.relationships.list_by_document(doc.id)
            assert len(edges) >= 1

            # job finished on the FINALIZE stage
            job = await verify.documents.get_job(doc.id)
            assert job.stage is ProcessingStage.FINALIZE
            assert job.stage_status == "succeeded"
    finally:
        await _cleanup(sf, doc.id)


async def test_failure_dead_letters_and_marks_document_failed(db):
    settings, sf = db
    store = InMemoryObjectStore()  # intentionally empty -> validate can't fetch the PDF
    owner = uuid4()
    pdf = b"%PDF-1.4 missing-in-store"
    doc = Document(
        owner_id=owner,
        filename="missing.pdf",
        content_hash=hashlib.sha256(pdf + b"x").hexdigest(),
        storage_uri=f"raw/{owner}/missing.pdf",
        mime_type="application/pdf",
        size_bytes=len(pdf),
    )
    uow = SqlAlchemyUnitOfWork(sf, settings)
    async with uow:
        await uow.documents.add(doc)
        # max_attempts=1 so the first failure goes straight to dead-letter.
        await uow.task_queue.enqueue(doc.id, ProcessingStage.VALIDATE, max_attempts=1)
        await uow.commit()

    engines = build_engines(settings, object_store=store)
    runner = PipelineRunner(sf, settings, engines)
    try:
        await runner.drain(max_iterations=10)
        verify = SqlAlchemyUnitOfWork(sf, settings)
        async with verify:
            d = await verify.documents.get(doc.id)
            assert d.status is ProcessingStatus.FAILED
        async with sf() as s:
            status = (
                await s.execute(
                    text("SELECT status FROM pipeline_tasks WHERE document_id=:d"),
                    {"d": str(doc.id)},
                )
            ).scalar_one()
        assert status == "dead"
    finally:
        await _cleanup(sf, doc.id)
