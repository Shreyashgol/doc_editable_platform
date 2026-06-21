"""Fast unit tests for the dependency-free adapters (no DB, no network)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from app.core.config import Settings
from app.core.errors import AuthenticationError
from app.domain.entities import Symbol
from app.domain.enums import ProcessingStage, RelationshipType, SymbolType
from app.domain.events import DocumentCompleted, DocumentUploaded
from app.domain.value_objects import BBox
from app.infrastructure.classification.rule_engine import RuleBasedClassifier
from app.infrastructure.embeddings.hash_embedder import HashEmbedder
from app.infrastructure.factories import build_embedder, build_object_store, build_ocr
from app.infrastructure.graph.inferrer import ProximityRelationshipInferrer
from app.infrastructure.messaging.event_publisher import (
    CollectingEventPublisher,
    PostgresEventPublisher,
)
from app.infrastructure.ocr.engines import NoOpOcrEngine
from app.infrastructure.security.jwt import JwtService
from app.infrastructure.security.passwords import hash_password, verify_password
from app.infrastructure.storage.s3 import InMemoryObjectStore


# --- rule classifier ---
@pytest.mark.parametrize(
    "label,expected",
    [
        ("XV-200", SymbolType.VALVE),
        ("PIC-300", SymbolType.CONTROLLER),  # longest-prefix wins over 'P'
        ("PT-100", SymbolType.PRESSURE_TRANSMITTER),
        ("P-101", SymbolType.PUMP),
        ("HEX-9", SymbolType.HEAT_EXCHANGER),
    ],
)
def test_rule_classifier_maps_prefixes(label, expected):
    c = RuleBasedClassifier()
    assert c.classify(label=label, crop_png=None).symbol_type is expected


def test_rule_classifier_unknown_paths():
    c = RuleBasedClassifier()
    assert c.classify(label=None, crop_png=None).symbol_type is SymbolType.UNKNOWN
    assert c.classify(label="???", crop_png=None).symbol_type is SymbolType.UNKNOWN


# --- hash embedder ---
def test_hash_embedder_deterministic_and_normalised():
    e = HashEmbedder(dim=512)
    v1 = e.embed_image(b"crop-bytes")
    v2 = e.embed_image(b"crop-bytes")
    assert v1 == v2 and len(v1) == 512
    assert abs(sum(x * x for x in v1) - 1.0) < 1e-6
    assert e.dim == 512 and "hash" in e.model_name
    assert len(e.embed_text("valve")) == 512


# --- proximity graph inferrer ---
def _sym(doc, x, y, t) -> Symbol:
    s = Symbol(document_id=doc, page_number=1, bbox=BBox(x, y, 10, 10), crop_uri="c.png")
    s.symbol_type = t
    return s


def test_inferrer_connects_role_symbol_to_nearest():
    doc = uuid4()
    pump = _sym(doc, 0, 0, SymbolType.PUMP)
    valve = _sym(doc, 30, 0, SymbolType.VALVE)
    edges = ProximityRelationshipInferrer().infer([pump, valve])
    assert any(e.source_symbol_id == pump.id and e.type is RelationshipType.FEEDS for e in edges)


def test_inferrer_skips_single_symbol_and_non_role_types():
    doc = uuid4()
    assert ProximityRelationshipInferrer().infer([_sym(doc, 0, 0, SymbolType.PUMP)]) == []
    tanks = [_sym(doc, 0, 0, SymbolType.TANK), _sym(doc, 20, 0, SymbolType.TANK)]
    assert ProximityRelationshipInferrer().infer(tanks) == []  # TANK has no relation mapping


# --- passwords ---
def test_password_hash_and_verify():
    h = hash_password("s3cret-pass")
    assert verify_password("s3cret-pass", h) is True
    assert verify_password("wrong", h) is False
    assert verify_password("x", "not-a-hash") is False


# --- jwt ---
def test_jwt_roundtrip_and_type_enforcement():
    jwt = JwtService(Settings())
    uid = uuid4()
    access = jwt.issue_access(uid, ["engineer"])
    claims = jwt.decode(access, expected_type="access")
    assert claims["sub"] == str(uid) and claims["roles"] == ["engineer"]
    with pytest.raises(AuthenticationError):
        jwt.decode(access, expected_type="refresh")
    with pytest.raises(AuthenticationError):
        jwt.decode("garbage.token.value")


# --- factories ---
def test_factories_default_to_dependency_free_backends():
    s = Settings(environment="test")
    assert isinstance(build_embedder(s), HashEmbedder)
    assert isinstance(build_ocr(s), NoOpOcrEngine)
    assert isinstance(build_object_store(s), InMemoryObjectStore)


def test_noop_ocr_returns_empty():
    assert NoOpOcrEngine().extract_text(b"png") == []


# --- event publisher ---
class _FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[UUID, ProcessingStage]] = []

    async def enqueue(self, document_id, stage, *, max_attempts, run_after_seconds=0.0, payload=None):
        self.enqueued.append((document_id, stage))

    async def claim_batch(self, *a, **k):  # pragma: no cover - unused here
        return []

    async def mark_succeeded(self, *a, **k): ...
    async def mark_retry(self, *a, **k): ...
    async def mark_dead(self, *a, **k): ...
    async def reclaim_expired(self, *a, **k):  # pragma: no cover - unused here
        return 0


async def test_collecting_publisher_records_events():
    pub = CollectingEventPublisher()
    await pub.publish(DocumentUploaded(aggregate_id=uuid4()))
    assert len(pub.events) == 1


async def test_postgres_publisher_enqueues_only_on_uploaded():
    q = _FakeQueue()
    pub = PostgresEventPublisher(q, max_attempts=5)
    doc_id = uuid4()
    await pub.publish(DocumentUploaded(aggregate_id=doc_id))
    await pub.publish(DocumentCompleted(aggregate_id=doc_id))  # ignored
    assert q.enqueued == [(doc_id, ProcessingStage.VALIDATE)]
