"""API tests for symbols, properties, versions, graph, and vector search.

Symbols are seeded directly via repositories (fast) so these tests don't run the full pipeline;
the pipeline itself is covered by the worker E2E tests.
"""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

import pytest
from app.core.container import Container
from app.domain.entities import Document, Symbol
from app.domain.enums import ClassificationMethod, SymbolType
from app.domain.value_objects import BBox, Classification
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from httpx import AsyncClient

pytestmark = pytest.mark.api


async def _seed(container: Container, owner_id: UUID) -> tuple[UUID, list[UUID]]:
    settings = container.settings
    uow = SqlAlchemyUnitOfWork(container.session_factory, settings)
    doc = Document(
        owner_id=owner_id,
        filename="seed.pdf",
        content_hash=hashlib.sha256(uuid4().bytes).hexdigest(),
        storage_uri="raw/seed.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        page_count=1,
    )
    pump = Symbol(document_id=doc.id, page_number=1, bbox=BBox(10, 10, 40, 40), crop_uri="c1.png")
    pump.apply_classification(Classification(SymbolType.PUMP, ClassificationMethod.RULE, 0.9, "P"))
    pump.assign_label("P-101")
    valve = Symbol(document_id=doc.id, page_number=1, bbox=BBox(80, 12, 40, 40), crop_uri="c2.png")
    valve.apply_classification(
        Classification(SymbolType.VALVE, ClassificationMethod.RULE, 0.9, "XV")
    )
    valve.assign_label("XV-200")

    async with uow:
        await uow.documents.add(doc)
        await uow.symbols.add_many([pump, valve])
        # distinct embeddings via the container's embedder (same space the API search uses)
        await uow.symbols.set_embedding(
            pump.id, container.embedder.model_name, container.embedder.embed_image(b"pump-crop")
        )
        await uow.symbols.set_embedding(
            valve.id, container.embedder.model_name, container.embedder.embed_image(b"valve-crop")
        )
        await uow.commit()
    return doc.id, [pump.id, valve.id]


async def test_list_and_get_symbols(client: AsyncClient, auth, container):
    headers, owner_id = auth
    doc_id, (pump_id, _valve_id) = await _seed(container, owner_id)

    listing = await client.get(f"/api/v1/documents/{doc_id}/symbols", headers=headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 2

    one = await client.get(f"/api/v1/symbols/{pump_id}", headers=headers)
    assert one.status_code == 200
    body = one.json()
    assert body["type"] == "Pump" and body["label"] == "P-101"
    assert body["has_embedding"] is True


async def test_edit_symbol_creates_version(client: AsyncClient, auth, container):
    headers, owner_id = auth
    _doc_id, (pump_id, _) = await _seed(container, owner_id)

    edit = await client.patch(
        f"/api/v1/symbols/{pump_id}",
        headers=headers,
        json={
            "bbox": {"x": 5, "y": 5, "width": 20, "height": 20},
            "rotation": 90,
            "type": "Compressor",
            "reason": "reclassified",
        },
    )
    assert edit.status_code == 200
    body = edit.json()
    assert body["version"] == 2
    assert body["type"] == "Compressor"
    assert body["bbox"] == {"x": 5, "y": 5, "width": 20, "height": 20}
    assert body["rotation"] == 90

    versions = await client.get(f"/api/v1/symbols/{pump_id}/versions", headers=headers)
    assert versions.status_code == 200
    vs = versions.json()
    assert len(vs) == 1
    # the stored version is the state BEFORE the edit
    assert vs[0]["version"] == 1
    assert vs[0]["snapshot"]["symbol_type"] == "Pump"


async def test_upsert_properties(client: AsyncClient, auth, container):
    headers, owner_id = auth
    _doc_id, (pump_id, _) = await _seed(container, owner_id)
    resp = await client.put(
        f"/api/v1/symbols/{pump_id}/properties",
        headers=headers,
        json={
            "properties": [
                {"key": "tag", "value_type": "string", "value": "P-101"},
                {"key": "flow_rate", "value_type": "number", "value": 42.5},
            ]
        },
    )
    assert resp.status_code == 200
    props = {p["key"]: p["value"] for p in resp.json()["properties"]}
    assert props == {"tag": "P-101", "flow_rate": 42.5}


async def test_graph_create_get_delete_edge(client: AsyncClient, auth, container):
    headers, owner_id = auth
    doc_id, (pump_id, valve_id) = await _seed(container, owner_id)

    created = await client.post(
        "/api/v1/relationships",
        headers=headers,
        json={
            "document_id": str(doc_id),
            "source_symbol_id": str(pump_id),
            "target_symbol_id": str(valve_id),
            "type": "feeds",
            "confidence": 0.8,
        },
    )
    assert created.status_code == 201
    edge_id = created.json()["id"]

    graph = await client.get(f"/api/v1/documents/{doc_id}/graph", headers=headers)
    assert graph.status_code == 200
    g = graph.json()
    assert len(g["nodes"]) == 2 and len(g["edges"]) == 1
    assert g["edges"][0]["type"] == "feeds"

    deleted = await client.delete(f"/api/v1/relationships/{edge_id}", headers=headers)
    assert deleted.status_code == 204
    graph2 = await client.get(f"/api/v1/documents/{doc_id}/graph", headers=headers)
    assert graph2.json()["edges"] == []


async def test_self_loop_edge_rejected(client: AsyncClient, auth, container):
    headers, owner_id = auth
    doc_id, (pump_id, _) = await _seed(container, owner_id)
    resp = await client.post(
        "/api/v1/relationships",
        headers=headers,
        json={
            "document_id": str(doc_id),
            "source_symbol_id": str(pump_id),
            "target_symbol_id": str(pump_id),
            "type": "feeds",
        },
    )
    assert resp.status_code == 422


async def test_search_by_symbol_id_ranks_self_first(client: AsyncClient, auth, container):
    headers, owner_id = auth
    _doc_id, (pump_id, _valve_id) = await _seed(container, owner_id)
    resp = await client.post(
        "/api/v1/search/similar",
        headers=headers,
        json={"symbol_id": str(pump_id), "top_k": 5},
    )
    assert resp.status_code == 200
    hits = resp.json()["hits"]
    assert hits[0]["symbol"]["id"] == str(pump_id)
    assert hits[0]["score"] >= hits[-1]["score"]


async def test_search_requires_exactly_one_query(client: AsyncClient, auth):
    headers, _ = auth
    resp = await client.post(
        "/api/v1/search/similar", headers=headers, json={"text": "valve", "top_k": 3}
    )
    assert resp.status_code == 200  # text-only is valid
    bad = await client.post(
        "/api/v1/search/similar",
        headers=headers,
        json={"text": "valve", "image_b64": "AAAA", "top_k": 3},
    )
    assert bad.status_code == 422  # two queries rejected by schema validation
