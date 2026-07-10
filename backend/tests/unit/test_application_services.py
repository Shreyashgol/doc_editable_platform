"""Unit tests for application services using in-memory fakes.

Covers auth_service, document_service, symbol_service, graph_service,
search_service, and the factories module to close the coverage gap.
"""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

import pytest
from app.application.security import Principal
from app.application.services.auth_service import AuthService
from app.application.services.document_service import DocumentService
from app.application.services.file_validation import FileValidator
from app.application.services.graph_service import GraphService
from app.application.services.search_service import SearchService
from app.application.services.symbol_service import PropertyInput, SymbolService
from app.application.unit_of_work import UnitOfWork
from app.core.config import Settings
from app.core.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ProcessingError,
    ValidationError,
)
from app.domain.entities import (
    AuditLog,
    Document,
    ProcessingJob,
    Relationship,
    Symbol,
    SymbolProperty,
    SymbolVersion,
    User,
)
from app.domain.enums import (
    ProcessingStage,
    ProcessingStatus,
    PropertyValueType,
    RelationshipType,
    Role,
    SymbolType,
)
from app.domain.events import DomainEvent
from app.domain.ports import (
    AuditRepository,
    DocumentRepository,
    Embedder,
    EventPublisher,
    ObjectStore,
    RelationshipRepository,
    SymbolRepository,
    TaskQueue,
    UserRepository,
    VirusScanner,
)
from app.domain.value_objects import BBox
from app.infrastructure.security.jwt import JwtService

# ─── In-memory fakes ──────────────────────────────────────────────────────────

class FakeDocumentRepository(DocumentRepository):
    def __init__(self) -> None:
        self._docs: dict[UUID, Document] = {}
        self._jobs: dict[UUID, ProcessingJob] = {}

    async def add(self, document: Document) -> Document:
        self._docs[document.id] = document
        return document

    async def get(self, document_id: UUID) -> Document | None:
        return self._docs.get(document_id)

    async def get_by_owner_and_hash(
        self, owner_id: UUID, content_hash: str
    ) -> Document | None:
        for d in self._docs.values():
            if d.owner_id == owner_id and d.content_hash == content_hash:
                return d
        return None

    async def update(self, document: Document) -> None:
        self._docs[document.id] = document

    async def list_by_owner(
        self,
        owner_id: UUID,
        *,
        status: ProcessingStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Document], int]:
        matches = [
            d for d in self._docs.values()
            if d.owner_id == owner_id
            and (status is None or d.status == status)
        ]
        total = len(matches)
        return matches[offset: offset + limit], total

    async def add_pages(self, pages) -> None:
        pass

    async def list_pages(self, document_id: UUID):
        return []

    async def delete_pages(self, document_id: UUID) -> None:
        pass

    async def get_job(self, document_id: UUID) -> ProcessingJob | None:
        return self._jobs.get(document_id)

    async def upsert_job(self, job: ProcessingJob) -> None:
        self._jobs[job.document_id] = job


class FakeSymbolRepository(SymbolRepository):
    def __init__(self) -> None:
        self._symbols: dict[UUID, Symbol] = {}
        self._versions: list[SymbolVersion] = []
        self._properties: dict[UUID, list[SymbolProperty]] = {}

    async def add_many(self, symbols: list[Symbol]) -> None:
        for s in symbols:
            self._symbols[s.id] = s

    async def delete_by_document(self, document_id: UUID) -> None:
        to_del = [k for k, v in self._symbols.items() if v.document_id == document_id]
        for k in to_del:
            del self._symbols[k]

    async def get(self, symbol_id: UUID) -> Symbol | None:
        return self._symbols.get(symbol_id)

    async def list_by_document(
        self, document_id: UUID, *, page_number: int | None = None
    ) -> list[Symbol]:
        return [
            s for s in self._symbols.values()
            if s.document_id == document_id
            and (page_number is None or s.page_number == page_number)
        ]

    async def update(self, symbol: Symbol) -> None:
        self._symbols[symbol.id] = symbol

    async def add_version(self, version: SymbolVersion) -> None:
        self._versions.append(version)

    async def list_versions(self, symbol_id: UUID) -> list[SymbolVersion]:
        return [v for v in self._versions if v.symbol_id == symbol_id]

    async def upsert_properties(
        self, symbol_id: UUID, properties: list[SymbolProperty]
    ) -> None:
        self._properties[symbol_id] = properties

    async def set_embedding(
        self, symbol_id: UUID, model: str, vector: list[float]
    ) -> None:
        sym = self._symbols.get(symbol_id)
        if sym:
            sym.embedding = vector

    async def search_similar(
        self,
        vector: list[float],
        *,
        top_k: int = 10,
        document_id: UUID | None = None,
        owner_id: UUID | None = None,
        symbol_type: str | None = None,
    ) -> list[tuple[Symbol, float]]:
        results = []
        for s in self._symbols.values():
            if document_id and s.document_id != document_id:
                continue
            if s.embedding is not None:
                results.append((s, 0.99))
        return results[:top_k]


class FakeRelationshipRepository(RelationshipRepository):
    def __init__(self) -> None:
        self._edges: dict[UUID, Relationship] = {}

    async def add(self, relationship: Relationship) -> Relationship:
        self._edges[relationship.id] = relationship
        return relationship

    async def add_many(self, relationships: list[Relationship]) -> None:
        for r in relationships:
            self._edges[r.id] = r

    async def delete(self, relationship_id: UUID) -> None:
        self._edges.pop(relationship_id, None)

    async def delete_by_document(self, document_id: UUID) -> None:
        to_del = [k for k, v in self._edges.items() if v.document_id == document_id]
        for k in to_del:
            del self._edges[k]

    async def get(self, relationship_id: UUID) -> Relationship | None:
        return self._edges.get(relationship_id)

    async def list_by_document(self, document_id: UUID) -> list[Relationship]:
        return [r for r in self._edges.values() if r.document_id == document_id]

    async def neighbours(
        self, symbol_id: UUID, *, depth: int = 1
    ) -> list[Relationship]:
        return [
            r for r in self._edges.values()
            if r.source_symbol_id == symbol_id or r.target_symbol_id == symbol_id
        ]


class FakeAuditRepository(AuditRepository):
    def __init__(self) -> None:
        self.entries: list[AuditLog] = []

    async def add(self, entry: AuditLog) -> None:
        self.entries.append(entry)

    async def query(self, **kwargs) -> list[AuditLog]:
        return self.entries


class FakeUserRepository(UserRepository):
    def __init__(self) -> None:
        self._users: dict[UUID, User] = {}

    async def get_by_email(self, email: str) -> User | None:
        for u in self._users.values():
            if u.email == email:
                return u
        return None

    async def get(self, user_id: UUID) -> User | None:
        return self._users.get(user_id)

    async def add(self, user: User) -> User:
        self._users[user.id] = user
        return user


class FakeTaskQueue(TaskQueue):
    def __init__(self) -> None:
        self.enqueued: list[tuple[UUID, ProcessingStage]] = []

    async def enqueue(
        self, document_id, stage, *, max_attempts, run_after_seconds=0.0, payload=None
    ):
        self.enqueued.append((document_id, stage))

    async def claim_batch(self, *a, **k):
        return []

    async def mark_succeeded(self, *a, **k): ...
    async def mark_retry(self, *a, **k): ...
    async def mark_dead(self, *a, **k): ...
    async def reclaim_expired(self, *a, **k):
        return 0


class FakeEventPublisher(EventPublisher):
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self.events.append(event)


class FakeObjectStore(ObjectStore):
    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, content_type: str) -> str:
        self._data[key] = data
        return key

    def get(self, key: str) -> bytes:
        return self._data[key]

    def presign_get(self, key: str, ttl_seconds: int) -> str:
        return f"https://fake/{key}"

    def delete_prefix(self, prefix: str) -> None:
        to_del = [k for k in self._data if k.startswith(prefix)]
        for k in to_del:
            del self._data[k]


class FakeVirusScanner(VirusScanner):
    def scan(self, data: bytes) -> None:
        return None


class FakeEmbedder(Embedder):
    def embed_image(self, crop_png: bytes) -> list[float]:
        return [0.1] * 512

    def embed_text(self, text: str) -> list[float]:
        return [0.2] * 512

    @property
    def model_name(self) -> str:
        return "fake"

    @property
    def dim(self) -> int:
        return 512


class FakeUnitOfWork(UnitOfWork):
    def __init__(self) -> None:
        self.documents = FakeDocumentRepository()
        self.symbols = FakeSymbolRepository()
        self.relationships = FakeRelationshipRepository()
        self.audit = FakeAuditRepository()
        self.users = FakeUserRepository()
        self.task_queue = FakeTaskQueue()
        self.events = FakeEventPublisher()
        self._committed = False

    async def __aenter__(self) -> FakeUnitOfWork:
        return self

    async def __aexit__(self, *exc) -> None:
        pass

    async def commit(self) -> None:
        self._committed = True

    async def rollback(self) -> None:
        pass


# ─── helpers ──────────────────────────────────────────────────────────────────

def _principal(user_id: UUID | None = None, admin: bool = False) -> Principal:
    roles = frozenset({Role.ADMIN}) if admin else frozenset({Role.ENGINEER})
    return Principal(user_id=user_id or uuid4(), roles=roles)


def _settings() -> Settings:
    return Settings(environment="test")


_PDF_MAGIC = b"%PDF-1.4 fake content for testing"


def _make_document(owner_id: UUID, **overrides) -> Document:
    defaults: dict[str, object] = {
        "owner_id": owner_id,
        "filename": "test.pdf",
        "content_hash": hashlib.sha256(_PDF_MAGIC).hexdigest(),
        "storage_uri": "raw/test.pdf",
        "mime_type": "application/pdf",
        "size_bytes": len(_PDF_MAGIC),
    }
    defaults.update(overrides)
    return Document(**defaults)


def _make_symbol(document_id: UUID, **overrides) -> Symbol:
    defaults: dict[str, object] = {
        "document_id": document_id,
        "page_number": 1,
        "bbox": BBox(10, 20, 30, 40),
        "crop_uri": "crops/sym.png",
    }
    defaults.update(overrides)
    return Symbol(**defaults)


# ═════════════════════════════════════════════════════════════════════════════
# AuthService tests
# ═════════════════════════════════════════════════════════════════════════════

class TestAuthService:
    def _make(self) -> tuple[AuthService, FakeUnitOfWork]:
        uow = FakeUnitOfWork()
        jwt = JwtService(_settings())
        return AuthService(uow, jwt), uow

    async def test_register_new_user(self):
        svc, uow = self._make()
        user = await svc.register("alice@example.com", "strong-password")
        assert user.email == "alice@example.com"
        assert Role.ENGINEER in user.roles

    async def test_register_duplicate_raises_conflict(self):
        svc, uow = self._make()
        await svc.register("bob@example.com", "password123")
        with pytest.raises(ConflictError):
            await svc.register("bob@example.com", "password123")

    async def test_authenticate_returns_tokens(self):
        svc, uow = self._make()
        await svc.register("user@test.com", "correct-pass")
        tokens = await svc.authenticate("user@test.com", "correct-pass")
        assert tokens.access_token
        assert tokens.refresh_token
        assert tokens.token_type == "bearer"

    async def test_authenticate_wrong_password_raises(self):
        svc, uow = self._make()
        await svc.register("user@test.com", "correct-pass")
        with pytest.raises(AuthenticationError):
            await svc.authenticate("user@test.com", "wrong-pass")

    async def test_authenticate_unknown_user_raises(self):
        svc, _ = self._make()
        with pytest.raises(AuthenticationError):
            await svc.authenticate("nobody@test.com", "pass")

    async def test_authenticate_inactive_user_raises(self):
        svc, uow = self._make()
        user = await svc.register("inactive@test.com", "pass")
        user.is_active = False
        with pytest.raises(AuthenticationError):
            await svc.authenticate("inactive@test.com", "pass")

    async def test_refresh_returns_new_tokens(self):
        svc, uow = self._make()
        await svc.register("user@test.com", "pass")
        tokens = await svc.authenticate("user@test.com", "pass")
        new_tokens = await svc.refresh(tokens.refresh_token)
        assert new_tokens.access_token
        assert new_tokens.refresh_token


# ═════════════════════════════════════════════════════════════════════════════
# DocumentService tests
# ═════════════════════════════════════════════════════════════════════════════

class TestDocumentService:
    def _make(self) -> tuple[DocumentService, FakeUnitOfWork, Principal]:
        uow = FakeUnitOfWork()
        settings = _settings()
        svc = DocumentService(
            uow,
            validator=FileValidator(settings),
            object_store=FakeObjectStore(),
            virus_scanner=FakeVirusScanner(),
            settings=settings,
        )
        principal = _principal()
        return svc, uow, principal

    async def test_upload_stores_document(self):
        svc, uow, p = self._make()
        result = await svc.upload(
            principal=p,
            filename="schematic.pdf",
            content=_PDF_MAGIC,
            declared_mime="application/pdf",
        )
        assert not result.deduplicated
        assert result.document.filename == "schematic.pdf"
        assert result.document.owner_id == p.user_id

    async def test_upload_deduplicates(self):
        svc, uow, p = self._make()
        r1 = await svc.upload(
            principal=p, filename="a.pdf", content=_PDF_MAGIC,
            declared_mime="application/pdf",
        )
        r2 = await svc.upload(
            principal=p, filename="b.pdf", content=_PDF_MAGIC,
            declared_mime="application/pdf",
        )
        assert r2.deduplicated
        assert r2.document.id == r1.document.id

    async def test_get_returns_owned_document(self):
        svc, uow, p = self._make()
        doc = _make_document(p.user_id)
        await uow.documents.add(doc)
        got = await svc.get(p, doc.id)
        assert got.id == doc.id

    async def test_get_missing_raises_not_found(self):
        svc, _, p = self._make()
        with pytest.raises(NotFoundError):
            await svc.get(p, uuid4())

    async def test_get_other_user_raises_authorization(self):
        svc, uow, p = self._make()
        doc = _make_document(uuid4())  # different owner
        await uow.documents.add(doc)
        with pytest.raises(AuthorizationError):
            await svc.get(p, doc.id)

    async def test_list_returns_user_documents(self):
        svc, uow, p = self._make()
        await uow.documents.add(_make_document(p.user_id, filename="a.pdf"))
        await uow.documents.add(_make_document(p.user_id, filename="b.pdf"))
        docs, total = await svc.list(p, status=None, limit=50, offset=0)
        assert total == 2

    async def test_status_returns_doc_and_job(self):
        svc, uow, p = self._make()
        doc = _make_document(p.user_id)
        await uow.documents.add(doc)
        d, job = await svc.status(p, doc.id)
        assert d.id == doc.id
        assert job is None  # no job yet

    async def test_status_not_found(self):
        svc, _, p = self._make()
        with pytest.raises(NotFoundError):
            await svc.status(p, uuid4())

    async def test_cancel_transitions_document(self):
        svc, uow, p = self._make()
        doc = _make_document(p.user_id)
        await uow.documents.add(doc)
        cancelled = await svc.cancel(p, doc.id)
        assert cancelled.status == ProcessingStatus.CANCELLED

    async def test_cancel_not_found(self):
        svc, _, p = self._make()
        with pytest.raises(NotFoundError):
            await svc.cancel(p, uuid4())

    async def test_reprocess_from_failed(self):
        svc, uow, p = self._make()
        doc = _make_document(p.user_id)
        doc.mark_failed("some error")
        await uow.documents.add(doc)
        result = await svc.reprocess(p, doc.id)
        assert result.status == ProcessingStatus.QUEUED

    async def test_reprocess_from_completed(self):
        svc, uow, p = self._make()
        doc = _make_document(p.user_id)
        # Walk the state machine to COMPLETED
        doc.transition_to(ProcessingStatus.VALIDATING)
        doc.transition_to(ProcessingStatus.QUEUED)
        doc.transition_to(ProcessingStatus.PROCESSING)
        doc.transition_to(ProcessingStatus.OCR_RUNNING)
        doc.transition_to(ProcessingStatus.CLASSIFYING)
        doc.transition_to(ProcessingStatus.EMBEDDING)
        doc.transition_to(ProcessingStatus.COMPLETED)
        await uow.documents.add(doc)
        result = await svc.reprocess(p, doc.id)
        # COMPLETED doesn't transition to QUEUED — stays COMPLETED but re-enqueues
        assert result.status == ProcessingStatus.COMPLETED

    async def test_reprocess_from_processing_raises(self):
        svc, uow, p = self._make()
        doc = _make_document(p.user_id)
        doc.transition_to(ProcessingStatus.VALIDATING)
        doc.transition_to(ProcessingStatus.QUEUED)
        doc.transition_to(ProcessingStatus.PROCESSING)
        await uow.documents.add(doc)
        with pytest.raises(ProcessingError):
            await svc.reprocess(p, doc.id)

    async def test_reprocess_not_found(self):
        svc, _, p = self._make()
        with pytest.raises(NotFoundError):
            await svc.reprocess(p, uuid4())


# ═════════════════════════════════════════════════════════════════════════════
# SymbolService tests
# ═════════════════════════════════════════════════════════════════════════════

class TestSymbolService:
    def _make(self) -> tuple[SymbolService, FakeUnitOfWork, Principal, Document]:
        uow = FakeUnitOfWork()
        svc = SymbolService(uow)
        principal = _principal()
        doc = _make_document(principal.user_id)
        return svc, uow, principal, doc

    async def _seed(self, uow, doc, sym=None):
        await uow.documents.add(doc)
        s = sym or _make_symbol(doc.id)
        await uow.symbols.add_many([s])
        return s

    async def test_get_symbol(self):
        svc, uow, p, doc = self._make()
        sym = await self._seed(uow, doc)
        got = await svc.get(p, sym.id)
        assert got.id == sym.id

    async def test_get_symbol_not_found(self):
        svc, uow, p, doc = self._make()
        await uow.documents.add(doc)
        with pytest.raises(NotFoundError):
            await svc.get(p, uuid4())

    async def test_list_by_document(self):
        svc, uow, p, doc = self._make()
        await self._seed(uow, doc)
        result = await svc.list_by_document(p, doc.id)
        assert len(result) == 1

    async def test_list_by_document_not_found(self):
        svc, uow, p, _ = self._make()
        with pytest.raises(NotFoundError):
            await svc.list_by_document(p, uuid4())

    async def test_edit_symbol(self):
        svc, uow, p, doc = self._make()
        sym = await self._seed(uow, doc)
        new_bbox = BBox(100, 200, 50, 60)
        edited = await svc.edit(
            p, sym.id,
            bbox=new_bbox,
            rotation=90.0,
            symbol_type=SymbolType.VALVE,
            label="XV-200",
        )
        assert edited.bbox == new_bbox
        assert edited.rotation == 90.0
        assert edited.symbol_type == SymbolType.VALVE
        assert edited.label == "XV-200"
        assert edited.version == 2

    async def test_upsert_properties(self):
        svc, uow, p, doc = self._make()
        sym = await self._seed(uow, doc)
        props = [
            PropertyInput(
                key="pressure", value_type=PropertyValueType.NUMBER, value=42.0
            ),
        ]
        result = await svc.upsert_properties(p, sym.id, props)
        assert result.id == sym.id

    async def test_list_versions(self):
        svc, uow, p, doc = self._make()
        sym = await self._seed(uow, doc)
        await svc.edit(p, sym.id, label="v2")
        versions = await svc.list_versions(p, sym.id)
        assert len(versions) == 1  # one prior version snapshot


# ═════════════════════════════════════════════════════════════════════════════
# GraphService tests
# ═════════════════════════════════════════════════════════════════════════════

class TestGraphService:
    def _make(self) -> tuple[GraphService, FakeUnitOfWork, Principal, Document]:
        uow = FakeUnitOfWork()
        svc = GraphService(uow)
        principal = _principal()
        doc = _make_document(principal.user_id)
        return svc, uow, principal, doc

    async def test_get_graph(self):
        svc, uow, p, doc = self._make()
        await uow.documents.add(doc)
        sym = _make_symbol(doc.id)
        await uow.symbols.add_many([sym])
        symbols, edges = await svc.get_graph(p, doc.id)
        assert len(symbols) == 1
        assert edges == []

    async def test_get_graph_not_found(self):
        svc, uow, p, _ = self._make()
        with pytest.raises(NotFoundError):
            await svc.get_graph(p, uuid4())

    async def test_add_edge(self):
        svc, uow, p, doc = self._make()
        await uow.documents.add(doc)
        s1 = _make_symbol(doc.id)
        s2 = _make_symbol(doc.id)
        await uow.symbols.add_many([s1, s2])
        edge = await svc.add_edge(
            p,
            document_id=doc.id,
            source_symbol_id=s1.id,
            target_symbol_id=s2.id,
            relationship_type=RelationshipType.FEEDS,
        )
        assert edge.type == RelationshipType.FEEDS

    async def test_add_edge_same_symbol_raises(self):
        svc, uow, p, doc = self._make()
        sid = uuid4()
        with pytest.raises(ValidationError):
            await svc.add_edge(
                p,
                document_id=doc.id,
                source_symbol_id=sid,
                target_symbol_id=sid,
                relationship_type=RelationshipType.FEEDS,
            )

    async def test_add_edge_document_not_found(self):
        svc, uow, p, _ = self._make()
        with pytest.raises(NotFoundError):
            await svc.add_edge(
                p,
                document_id=uuid4(),
                source_symbol_id=uuid4(),
                target_symbol_id=uuid4(),
                relationship_type=RelationshipType.FEEDS,
            )

    async def test_add_edge_symbol_not_in_document(self):
        svc, uow, p, doc = self._make()
        await uow.documents.add(doc)
        s1 = _make_symbol(doc.id)
        await uow.symbols.add_many([s1])
        with pytest.raises(ValidationError):
            await svc.add_edge(
                p,
                document_id=doc.id,
                source_symbol_id=s1.id,
                target_symbol_id=uuid4(),  # does not exist
                relationship_type=RelationshipType.FEEDS,
            )

    async def test_delete_edge(self):
        svc, uow, p, doc = self._make()
        await uow.documents.add(doc)
        s1 = _make_symbol(doc.id)
        s2 = _make_symbol(doc.id)
        await uow.symbols.add_many([s1, s2])
        edge = await svc.add_edge(
            p,
            document_id=doc.id,
            source_symbol_id=s1.id,
            target_symbol_id=s2.id,
            relationship_type=RelationshipType.CONTROLS,
        )
        await svc.delete_edge(p, edge.id)
        assert await uow.relationships.get(edge.id) is None

    async def test_delete_edge_not_found(self):
        svc, uow, p, _ = self._make()
        with pytest.raises(NotFoundError):
            await svc.delete_edge(p, uuid4())


# ═════════════════════════════════════════════════════════════════════════════
# SearchService tests
# ═════════════════════════════════════════════════════════════════════════════

class TestSearchService:
    def _make(self) -> tuple[SearchService, FakeUnitOfWork, Principal, Document]:
        uow = FakeUnitOfWork()
        svc = SearchService(uow, FakeEmbedder())
        principal = _principal()
        doc = _make_document(principal.user_id)
        return svc, uow, principal, doc

    async def test_similar_by_text(self):
        svc, uow, p, doc = self._make()
        await uow.documents.add(doc)
        sym = _make_symbol(doc.id, embedding=[0.1] * 512)
        await uow.symbols.add_many([sym])
        hits = await svc.similar(p, text="valve")
        assert len(hits) >= 1

    async def test_similar_by_symbol_id(self):
        svc, uow, p, doc = self._make()
        await uow.documents.add(doc)
        sym = _make_symbol(doc.id, embedding=[0.1] * 512)
        await uow.symbols.add_many([sym])
        hits = await svc.similar(p, symbol_id=sym.id)
        assert len(hits) >= 1

    async def test_similar_symbol_not_found(self):
        svc, uow, p, _ = self._make()
        with pytest.raises(NotFoundError):
            await svc.similar(p, symbol_id=uuid4())

    async def test_similar_symbol_no_embedding(self):
        svc, uow, p, doc = self._make()
        await uow.documents.add(doc)
        sym = _make_symbol(doc.id)  # no embedding
        await uow.symbols.add_many([sym])
        with pytest.raises(ValidationError):
            await svc.similar(p, symbol_id=sym.id)

    async def test_similar_by_image_b64(self):
        import base64
        svc, uow, p, doc = self._make()
        await uow.documents.add(doc)
        sym = _make_symbol(doc.id, embedding=[0.1] * 512)
        await uow.symbols.add_many([sym])
        img = base64.b64encode(b"fakepng").decode()
        hits = await svc.similar(p, image_b64=img)
        assert len(hits) >= 1

    async def test_similar_bad_b64_raises(self):
        svc, uow, p, _ = self._make()
        with pytest.raises(ValidationError, match="not valid base64"):
            await svc.similar(p, image_b64="not!valid!base64!!!")

    async def test_similar_no_query_raises(self):
        svc, uow, p, _ = self._make()
        with pytest.raises(ValidationError):
            await svc.similar(p)

    async def test_similar_multiple_queries_raises(self):
        svc, uow, p, _ = self._make()
        with pytest.raises(ValidationError):
            await svc.similar(p, text="a", image_b64="b")

    async def test_similar_scoped_to_document(self):
        svc, uow, p, doc = self._make()
        await uow.documents.add(doc)
        sym = _make_symbol(doc.id, embedding=[0.1] * 512)
        await uow.symbols.add_many([sym])
        hits = await svc.similar(p, text="valve", document_id=doc.id)
        assert len(hits) >= 1

    async def test_similar_document_scope_not_found(self):
        svc, uow, p, _ = self._make()
        with pytest.raises(NotFoundError):
            await svc.similar(p, text="valve", document_id=uuid4())

    async def test_admin_searches_globally(self):
        uow = FakeUnitOfWork()
        svc = SearchService(uow, FakeEmbedder())
        admin = _principal(admin=True)
        doc = _make_document(uuid4())  # other user's doc
        await uow.documents.add(doc)
        sym = _make_symbol(doc.id, embedding=[0.1] * 512)
        await uow.symbols.add_many([sym])
        hits = await svc.similar(admin, text="valve")
        assert len(hits) >= 1


# ═════════════════════════════════════════════════════════════════════════════
# Factory coverage
# ═════════════════════════════════════════════════════════════════════════════

def test_build_object_store_postgres_backend():
    from app.infrastructure.factories import build_object_store
    s = Settings(environment="local", object_store_backend="postgres")
    store = build_object_store(s)
    # Should return a PostgresObjectStore
    assert store is not None


def test_build_object_store_s3_no_endpoint():
    from app.infrastructure.factories import build_object_store
    s = Settings(environment="local", object_store_backend="s3", s3_endpoint_url=None)
    store = build_object_store(s)
    from app.infrastructure.storage.s3 import InMemoryObjectStore
    assert isinstance(store, InMemoryObjectStore)
