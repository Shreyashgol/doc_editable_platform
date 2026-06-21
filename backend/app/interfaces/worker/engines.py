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
from ...infrastructure.factories import build_embedder, build_object_store, build_ocr
from ...infrastructure.graph.inferrer import ProximityRelationshipInferrer


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
