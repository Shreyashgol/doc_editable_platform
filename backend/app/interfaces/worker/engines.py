"""Worker compute engines, selected from configuration (the worker's composition root)."""

from __future__ import annotations

from dataclasses import dataclass

from ...core.config import Settings
from ...domain.ports import (
    Embedder,
    ObjectStore,
    OcrEngine,
    PdfParser,
    RelationshipInferrer,
    SymbolClassifier,
    SymbolExtractor,
)
from ...infrastructure.classification.rule_engine import RuleBasedClassifier
from ...infrastructure.cv.pdf_parser import PyMuPdfParser
from ...infrastructure.cv.symbol_extractor import OpenCvSymbolExtractor
from ...infrastructure.embeddings.hash_embedder import HashEmbedder
from ...infrastructure.graph.inferrer import ProximityRelationshipInferrer
from ...infrastructure.ocr.engines import NoOpOcrEngine
from ...infrastructure.storage.s3 import InMemoryObjectStore, S3ObjectStore


@dataclass
class WorkerEngines:
    parser: PdfParser
    extractor: SymbolExtractor
    ocr: OcrEngine
    classifier: SymbolClassifier
    embedder: Embedder
    inferrer: RelationshipInferrer
    object_store: ObjectStore
    settings: Settings


def build_object_store(settings: Settings) -> ObjectStore:
    if settings.environment == "test" or settings.s3_endpoint_url is None:
        return InMemoryObjectStore()
    return S3ObjectStore(settings)


def build_ocr(settings: Settings) -> OcrEngine:
    if settings.ocr_backend == "paddle":  # pragma: no cover - heavy
        from ...infrastructure.ocr.engines import PaddleOcrEngine

        return PaddleOcrEngine()
    return NoOpOcrEngine()


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_backend == "openclip":  # pragma: no cover - heavy
        from ...infrastructure.embeddings.openclip_embedder import OpenClipEmbedder

        return OpenClipEmbedder(
            settings.embedding_model, settings.embedding_pretrained, settings.embedding_dim
        )
    return HashEmbedder(dim=settings.embedding_dim)


def build_engines(
    settings: Settings, *, object_store: ObjectStore | None = None
) -> WorkerEngines:
    return WorkerEngines(
        parser=PyMuPdfParser(),
        extractor=OpenCvSymbolExtractor(),
        ocr=build_ocr(settings),
        classifier=RuleBasedClassifier(),
        embedder=build_embedder(settings),
        inferrer=ProximityRelationshipInferrer(),
        object_store=object_store or build_object_store(settings),
        settings=settings,
    )
