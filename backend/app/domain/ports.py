"""Ports — interfaces the domain/application depend on, implemented by infrastructure adapters.

This is the seam that makes the system extensible: swapping PaddleOCR for Tesseract, OpenCLIP
for a fine-tuned model, or the Postgres graph for Neo4j means writing one adapter here, with
zero changes to domain or application code (ADR 0001, 0004).

Repositories are async (they back the async API and async SQLAlchemy). Heavy compute engines
are synchronous because they run inside Celery worker processes; async contexts call them via
``asyncio.to_thread``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from .entities import (
    AuditLog,
    Document,
    Page,
    ProcessingJob,
    Relationship,
    Symbol,
    SymbolProperty,
    SymbolVersion,
    User,
)
from .enums import ProcessingStage, ProcessingStatus
from .events import DomainEvent
from .value_objects import BBox, ClaimedTask, Classification, OcrToken


# --------------------------------------------------------------------------- repositories
class DocumentRepository(ABC):
    @abstractmethod
    async def add(self, document: Document) -> Document: ...

    @abstractmethod
    async def get(self, document_id: UUID) -> Document | None: ...

    @abstractmethod
    async def get_by_owner_and_hash(self, owner_id: UUID, content_hash: str) -> Document | None: ...

    @abstractmethod
    async def update(self, document: Document) -> None: ...

    @abstractmethod
    async def list_by_owner(
        self,
        owner_id: UUID,
        *,
        status: ProcessingStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Document], int]: ...

    @abstractmethod
    async def add_pages(self, pages: list[Page]) -> None: ...

    @abstractmethod
    async def get_job(self, document_id: UUID) -> ProcessingJob | None: ...

    @abstractmethod
    async def upsert_job(self, job: ProcessingJob) -> None: ...


class SymbolRepository(ABC):
    @abstractmethod
    async def add_many(self, symbols: list[Symbol]) -> None: ...

    @abstractmethod
    async def get(self, symbol_id: UUID) -> Symbol | None: ...

    @abstractmethod
    async def list_by_document(
        self, document_id: UUID, *, page_number: int | None = None
    ) -> list[Symbol]: ...

    @abstractmethod
    async def update(self, symbol: Symbol) -> None: ...

    @abstractmethod
    async def add_version(self, version: SymbolVersion) -> None: ...

    @abstractmethod
    async def list_versions(self, symbol_id: UUID) -> list[SymbolVersion]: ...

    @abstractmethod
    async def upsert_properties(
        self, symbol_id: UUID, properties: list[SymbolProperty]
    ) -> None: ...

    @abstractmethod
    async def set_embedding(self, symbol_id: UUID, model: str, vector: list[float]) -> None: ...

    @abstractmethod
    async def search_similar(
        self,
        vector: list[float],
        *,
        top_k: int = 10,
        document_id: UUID | None = None,
        symbol_type: str | None = None,
    ) -> list[tuple[Symbol, float]]:
        """Return (symbol, similarity_score) ordered by score desc. Hides the vector backend."""
        ...


class RelationshipRepository(ABC):
    """Graph edge persistence. Postgres adjacency-list now; Neo4j adapter later (ADR 0002)."""

    @abstractmethod
    async def add(self, relationship: Relationship) -> Relationship: ...

    @abstractmethod
    async def add_many(self, relationships: list[Relationship]) -> None: ...

    @abstractmethod
    async def delete(self, relationship_id: UUID) -> None: ...

    @abstractmethod
    async def list_by_document(self, document_id: UUID) -> list[Relationship]: ...

    @abstractmethod
    async def neighbours(self, symbol_id: UUID, *, depth: int = 1) -> list[Relationship]: ...


class AuditRepository(ABC):
    @abstractmethod
    async def add(self, entry: AuditLog) -> None: ...

    @abstractmethod
    async def query(
        self,
        *,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        actor_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]: ...


class UserRepository(ABC):
    @abstractmethod
    async def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    async def get(self, user_id: UUID) -> User | None: ...

    @abstractmethod
    async def add(self, user: User) -> User: ...


# --------------------------------------------------------------------------- infrastructure
class ObjectStore(ABC):
    """Artifact storage (MinIO/S3). Synchronous boto3-style; async callers wrap in to_thread."""

    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str) -> str: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def presign_get(self, key: str, ttl_seconds: int) -> str: ...

    @abstractmethod
    def delete_prefix(self, prefix: str) -> None: ...


class EventPublisher(ABC):
    @abstractmethod
    async def publish(self, event: DomainEvent) -> None: ...


class TaskQueue(ABC):
    """Durable job queue backed by Postgres (ADR 0005). The same abstraction would be
    satisfied by a broker adapter, so the worker and enqueuer never depend on the transport."""

    @abstractmethod
    async def enqueue(
        self,
        document_id: UUID,
        stage: ProcessingStage,
        *,
        max_attempts: int,
        run_after_seconds: float = 0.0,
        payload: dict[str, object] | None = None,
    ) -> None:
        """Insert (idempotently per document+stage) a task to run at/after the given delay."""
        ...

    @abstractmethod
    async def claim_batch(
        self, worker_id: str, *, limit: int, visibility_timeout_seconds: int
    ) -> list[ClaimedTask]:
        """Atomically lease up to ``limit`` due tasks (FOR UPDATE SKIP LOCKED)."""
        ...

    @abstractmethod
    async def mark_succeeded(self, task_id: UUID) -> None: ...

    @abstractmethod
    async def mark_retry(self, task_id: UUID, *, error: str, run_after_seconds: float) -> None: ...

    @abstractmethod
    async def mark_dead(self, task_id: UUID, *, error: str) -> None: ...

    @abstractmethod
    async def reclaim_expired(self, *, visibility_timeout_seconds: int) -> int:
        """Return expired leases (crashed workers) to the pending pool. Returns count reclaimed."""
        ...


# --------------------------------------------------------------------------- compute engines
class PdfParser(ABC):
    @abstractmethod
    def page_count(self, pdf_bytes: bytes) -> int: ...

    @abstractmethod
    def render_pages(self, pdf_bytes: bytes, dpi: int) -> list[tuple[int, bytes, int, int]]:
        """Return [(page_number, png_bytes, width_px, height_px), ...]."""
        ...

    @abstractmethod
    def validate_safety(
        self, pdf_bytes: bytes, *, max_pages: int, max_page_pixels: int
    ) -> None:
        """Raise PdfBombError if the document exceeds safety limits."""
        ...


class SymbolExtractor(ABC):
    @abstractmethod
    def extract(self, page_png: bytes, page_number: int) -> list[tuple[BBox, bytes]]:
        """CV pipeline → list of (bbox, crop_png_bytes) symbol candidates for one page."""
        ...


class OcrEngine(ABC):
    @abstractmethod
    def extract_text(self, page_png: bytes) -> list[OcrToken]: ...


class SymbolClassifier(ABC):
    """Strategy: rule engine (v1) → ML (v2) → ViT (v3). Selected by config/DI (ADR 0004)."""

    @abstractmethod
    def classify(self, *, label: str | None, crop_png: bytes | None) -> Classification: ...


class Embedder(ABC):
    @abstractmethod
    def embed_image(self, crop_png: bytes) -> list[float]: ...

    @abstractmethod
    def embed_text(self, text: str) -> list[float]: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def dim(self) -> int: ...


class VirusScanner(ABC):
    @abstractmethod
    def scan(self, data: bytes) -> None:
        """Raise VirusDetectedError if infected; return None if clean."""
        ...


class RelationshipInferrer(ABC):
    """Infers graph edges from symbol geometry/type/labels. Pluggable like classifiers."""

    @abstractmethod
    def infer(self, symbols: list[Symbol]) -> list[Relationship]: ...
