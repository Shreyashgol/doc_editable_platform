"""Factories that select concrete engine adapters from configuration.

Shared by the API container (which needs an Embedder for search) and the worker. The embedder
chosen here MUST match the one the worker used to create stored vectors, or similarity is
meaningless — both default to HashEmbedder(dim=512).
"""

from __future__ import annotations

from ..core.config import Settings
from ..domain.ports import Embedder, ObjectStore, OcrEngine
from .embeddings.hash_embedder import HashEmbedder
from .ocr.engines import NoOpOcrEngine
from .storage.s3 import InMemoryObjectStore, S3ObjectStore


def build_object_store(settings: Settings) -> ObjectStore:
    if settings.environment == "test":
        return InMemoryObjectStore()
    if settings.object_store_backend == "postgres":
        from .storage.postgres_store import PostgresObjectStore

        return PostgresObjectStore(settings)
    if settings.s3_endpoint_url is None:
        return InMemoryObjectStore()
    return S3ObjectStore(settings)


def build_ocr(settings: Settings) -> OcrEngine:
    if settings.ocr_backend == "paddle":  # pragma: no cover - heavy
        from .ocr.engines import PaddleOcrEngine

        return PaddleOcrEngine()
    return NoOpOcrEngine()


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_backend == "openclip":  # pragma: no cover - heavy
        from .embeddings.openclip_embedder import OpenClipEmbedder

        return OpenClipEmbedder(
            settings.embedding_model, settings.embedding_pretrained, settings.embedding_dim
        )
    return HashEmbedder(dim=settings.embedding_dim)
