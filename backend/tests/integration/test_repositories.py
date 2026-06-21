"""Repository integration tests against real Postgres + pgvector."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.domain.entities import (
    AuditLog,
    Document,
    Relationship,
    Symbol,
    SymbolProperty,
    User,
)
from app.domain.enums import (
    ClassificationMethod,
    ProcessingStatus,
    PropertyValueType,
    RelationshipType,
    Role,
    SymbolType,
)
from app.domain.value_objects import BBox, Classification
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.document_repository import SqlAlchemyDocumentRepository
from app.infrastructure.repositories.relationship_repository import (
    SqlAlchemyRelationshipRepository,
)
from app.infrastructure.repositories.symbol_repository import SqlAlchemySymbolRepository
from app.infrastructure.repositories.user_repository import SqlAlchemyUserRepository

pytestmark = pytest.mark.integration


async def test_document_crud_and_dedupe(session):
    repo = SqlAlchemyDocumentRepository(session)
    owner = uuid4()
    chash = "b" * 64
    doc = Document(
        owner_id=owner,
        filename="d.pdf",
        content_hash=chash,
        storage_uri="raw/d.pdf",
        mime_type="application/pdf",
        size_bytes=2048,
    )
    await repo.add(doc)

    fetched = await repo.get(doc.id)
    assert fetched is not None and fetched.filename == "d.pdf"
    assert fetched.status is ProcessingStatus.UPLOADED

    # dedupe lookup
    dupe = await repo.get_by_owner_and_hash(owner, chash)
    assert dupe is not None and dupe.id == doc.id

    # state transition persisted
    doc.transition_to(ProcessingStatus.VALIDATING)
    doc.page_count = 3
    await repo.update(doc)
    reread = await repo.get(doc.id)
    assert reread.status is ProcessingStatus.VALIDATING
    assert reread.page_count == 3

    docs, total = await repo.list_by_owner(owner, status=ProcessingStatus.VALIDATING)
    assert total == 1 and docs[0].id == doc.id


async def test_processing_job_upsert(session):
    repo = SqlAlchemyDocumentRepository(session)
    owner = uuid4()
    doc = Document(
        owner_id=owner, filename="j.pdf", content_hash="c" * 64,
        storage_uri="raw/j.pdf", mime_type="application/pdf", size_bytes=10,
    )
    await repo.add(doc)
    job = await repo.get_job(doc.id)
    assert job is None

    from app.domain.entities import ProcessingJob
    from app.domain.enums import ProcessingStage

    new_job = ProcessingJob(document_id=doc.id)
    new_job.record_attempt(ProcessingStage.PDF_EXTRACT)
    await repo.upsert_job(new_job)
    loaded = await repo.get_job(doc.id)
    assert loaded.stage is ProcessingStage.PDF_EXTRACT and loaded.attempts == 1

    new_job.succeed(1.5)
    await repo.upsert_job(new_job)
    loaded2 = await repo.get_job(doc.id)
    assert loaded2.stage_status == "succeeded"
    assert loaded2.timings["pdf_extract"] == 1.5


async def test_symbol_lifecycle_properties_and_versions(session):
    drepo = SqlAlchemyDocumentRepository(session)
    srepo = SqlAlchemySymbolRepository(session)
    owner = uuid4()
    doc = Document(
        owner_id=owner, filename="s.pdf", content_hash="d" * 64,
        storage_uri="raw/s.pdf", mime_type="application/pdf", size_bytes=10,
    )
    await drepo.add(doc)

    sym = Symbol(
        document_id=doc.id, page_number=1, bbox=BBox(10, 10, 30, 40),
        crop_uri="crops/s.png",
    )
    sym.apply_classification(
        Classification(SymbolType.VALVE, ClassificationMethod.RULE, 0.9, "XV")
    )
    sym.assign_label("XV-200")
    await srepo.add_many([sym])

    loaded = await srepo.get(sym.id)
    assert loaded.symbol_type is SymbolType.VALVE
    assert loaded.label == "XV-200"
    assert loaded.bbox == BBox(10, 10, 30, 40)

    # edit -> version
    prior = loaded.edit_geometry(bbox=BBox(5, 5, 20, 20), rotation=90, changed_by=owner)
    await srepo.add_version(prior)
    await srepo.update(loaded)
    versions = await srepo.list_versions(sym.id)
    assert len(versions) == 1 and versions[0].version == 1
    reread = await srepo.get(sym.id)
    assert reread.version == 2 and reread.bbox == BBox(5, 5, 20, 20)

    # typed properties upsert (replace-set)
    props = [
        SymbolProperty(symbol_id=sym.id, key="tag", value_type=PropertyValueType.STRING,
                       value="XV-200"),
        SymbolProperty(symbol_id=sym.id, key="pressure", value_type=PropertyValueType.NUMBER,
                       value=12.5),
    ]
    await srepo.upsert_properties(sym.id, props)
    withprops = await srepo.get(sym.id)
    keyed = {p.key: p.value for p in withprops.properties}
    assert keyed == {"tag": "XV-200", "pressure": 12.5}


async def test_embedding_and_similarity_search(session):
    drepo = SqlAlchemyDocumentRepository(session)
    srepo = SqlAlchemySymbolRepository(session)
    owner = uuid4()
    doc = Document(
        owner_id=owner, filename="e.pdf", content_hash="e" * 64,
        storage_uri="raw/e.pdf", mime_type="application/pdf", size_bytes=10,
    )
    await drepo.add(doc)

    dim = 512
    base = [0.0] * dim
    a = Symbol(document_id=doc.id, page_number=1, bbox=BBox(0, 0, 10, 10), crop_uri="a.png")
    b = Symbol(document_id=doc.id, page_number=1, bbox=BBox(20, 0, 10, 10), crop_uri="b.png")
    c = Symbol(document_id=doc.id, page_number=1, bbox=BBox(40, 0, 10, 10), crop_uri="c.png")
    await srepo.add_many([a, b, c])

    va = base.copy(); va[0] = 1.0
    vb = base.copy(); vb[0] = 0.9; vb[1] = 0.1
    vc = base.copy(); vc[5] = 1.0
    await srepo.set_embedding(a.id, "ViT-B-32", va)
    await srepo.set_embedding(b.id, "ViT-B-32", vb)
    await srepo.set_embedding(c.id, "ViT-B-32", vc)

    query = base.copy(); query[0] = 1.0
    results = await srepo.search_similar(query, top_k=3, document_id=doc.id)
    assert [s.id for s, _ in results][0] == a.id  # exact match ranks first
    assert results[0][1] > results[-1][1]  # similarity ordered descending


async def test_relationship_graph_and_neighbours(session):
    drepo = SqlAlchemyDocumentRepository(session)
    srepo = SqlAlchemySymbolRepository(session)
    rrepo = SqlAlchemyRelationshipRepository(session)
    owner = uuid4()
    doc = Document(
        owner_id=owner, filename="g.pdf", content_hash="f" * 64,
        storage_uri="raw/g.pdf", mime_type="application/pdf", size_bytes=10,
    )
    await drepo.add(doc)
    pump = Symbol(document_id=doc.id, page_number=1, bbox=BBox(0, 0, 10, 10), crop_uri="p.png")
    valve = Symbol(document_id=doc.id, page_number=1, bbox=BBox(20, 0, 10, 10), crop_uri="v.png")
    hx = Symbol(document_id=doc.id, page_number=1, bbox=BBox(40, 0, 10, 10), crop_uri="h.png")
    await srepo.add_many([pump, valve, hx])

    await rrepo.add(Relationship(doc.id, pump.id, valve.id, RelationshipType.FEEDS))
    await rrepo.add(Relationship(doc.id, valve.id, hx.id, RelationshipType.CONTROLS))

    edges = await rrepo.list_by_document(doc.id)
    assert len(edges) == 2

    direct = await rrepo.neighbours(pump.id, depth=1)
    assert len(direct) == 1 and direct[0].target_symbol_id == valve.id

    two_hop = await rrepo.neighbours(pump.id, depth=2)
    assert len(two_hop) == 2  # reaches valve and hx


async def test_user_and_audit_repositories(session):
    urepo = SqlAlchemyUserRepository(session)
    arepo = SqlAlchemyAuditRepository(session)
    user = User(email="Eng@Example.com", password_hash="x", roles={Role.ENGINEER})
    await urepo.add(user)
    found = await urepo.get_by_email("eng@example.com")  # case-insensitive
    assert found is not None and Role.ENGINEER in found.roles

    entry = AuditLog(
        actor_id=user.id, entity_type="document", entity_id=uuid4(), action="upload",
        correlation_id="corr-1",
    )
    await arepo.add(entry)
    results = await arepo.query(entity_type="document")
    assert any(a.action == "upload" for a in results)
