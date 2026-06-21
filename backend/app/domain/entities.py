"""Domain entities and aggregate roots.

Entities have identity and lifecycle. Behaviour that protects invariants lives here, not in
services or repositories — the document state machine is enforced by ``Document.transition_to``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from ..core.errors import IllegalStateTransitionError
from .enums import (
    ALLOWED_TRANSITIONS,
    ClassificationMethod,
    ProcessingStage,
    ProcessingStatus,
    PropertyValueType,
    RelationshipType,
    Role,
    SymbolType,
)
from .value_objects import BBox, Centroid, Classification


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Page:
    document_id: UUID
    page_number: int
    width_px: int
    height_px: int
    dpi: int
    render_uri: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)


@dataclass(slots=True)
class ProcessingJob:
    """Tracks the current pipeline position and retry accounting for a document."""

    document_id: UUID
    stage: ProcessingStage = ProcessingStage.VALIDATE
    stage_status: str = "pending"
    attempts: int = 0
    max_attempts: int = 5
    last_error: str | None = None
    timings: dict[str, float] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def record_attempt(self, stage: ProcessingStage) -> None:
        self.stage = stage
        self.attempts += 1
        self.stage_status = "running"
        self.started_at = _now()
        self.updated_at = _now()

    def succeed(self, duration_seconds: float) -> None:
        self.stage_status = "succeeded"
        self.finished_at = _now()
        self.timings[self.stage.value] = duration_seconds
        self.last_error = None
        self.updated_at = _now()

    def fail(self, error: str) -> None:
        self.stage_status = "failed"
        self.last_error = error
        self.updated_at = _now()

    @property
    def can_retry(self) -> bool:
        return self.attempts < self.max_attempts


@dataclass(slots=True)
class Document:
    """Aggregate root for an uploaded PDF and its processing lifecycle."""

    owner_id: UUID
    filename: str
    content_hash: str
    storage_uri: str
    mime_type: str
    size_bytes: int
    page_count: int = 0
    status: ProcessingStatus = ProcessingStatus.UPLOADED
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    # Recorded transitions so the pipeline is fully auditable/resumable.
    transitions: list[tuple[ProcessingStatus, ProcessingStatus, datetime]] = field(
        default_factory=list
    )

    def transition_to(self, target: ProcessingStatus) -> None:
        """Enforce the state machine. Raises on an illegal move."""
        allowed = ALLOWED_TRANSITIONS.get(self.status, frozenset())
        if target not in allowed:
            raise IllegalStateTransitionError(
                f"Cannot transition document {self.id} from {self.status.value} to {target.value}"
            )
        self.transitions.append((self.status, target, _now()))
        self.status = target
        self.updated_at = _now()

    def mark_failed(self, reason: str) -> None:
        # FAILED is reachable from ANY non-terminal state (see docs/02 state machine), so this
        # bypasses the strict forward-transition table rather than enumerating every source.
        if self.status.is_terminal:
            return
        self.transitions.append((self.status, ProcessingStatus.FAILED, _now()))
        self.status = ProcessingStatus.FAILED
        self.updated_at = _now()

    def cancel(self) -> None:
        if self.status.is_terminal:
            raise IllegalStateTransitionError(
                f"Document {self.id} is already terminal ({self.status.value})"
            )
        self.transition_to(ProcessingStatus.CANCELLED)


@dataclass(slots=True)
class SymbolProperty:
    symbol_id: UUID
    key: str
    value_type: PropertyValueType
    value: object
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


@dataclass(slots=True)
class SymbolVersion:
    """Immutable snapshot of a symbol's editable state at a point in time."""

    symbol_id: UUID
    version: int
    snapshot: dict[str, object]
    changed_by: UUID | None
    change_reason: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)


@dataclass(slots=True)
class Symbol:
    """Aggregate root: a first-class, editable, searchable symbol object."""

    document_id: UUID
    page_number: int
    bbox: BBox
    crop_uri: str
    symbol_type: SymbolType = SymbolType.UNKNOWN
    label: str | None = None
    rotation: float = 0.0
    classification_method: ClassificationMethod | None = None
    classification_confidence: float | None = None
    embedding: list[float] | None = None
    version: int = 1
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    properties: list[SymbolProperty] = field(default_factory=list)

    @property
    def centroid(self) -> Centroid:
        return self.bbox.centroid

    def apply_classification(self, classification: Classification) -> None:
        self.symbol_type = classification.symbol_type
        self.classification_method = classification.method
        self.classification_confidence = classification.confidence
        self.updated_at = _now()

    def assign_label(self, label: str) -> None:
        self.label = label
        self.updated_at = _now()

    def set_embedding(self, vector: list[float]) -> None:
        self.embedding = vector
        self.updated_at = _now()

    def snapshot(self) -> dict[str, object]:
        return {
            "bbox": self.bbox.to_dict(),
            "rotation": self.rotation,
            "symbol_type": self.symbol_type.value,
            "label": self.label,
            "properties": [
                {"key": p.key, "value_type": p.value_type.value, "value": p.value}
                for p in self.properties
            ],
        }

    def edit_geometry(
        self,
        *,
        bbox: BBox | None = None,
        rotation: float | None = None,
        changed_by: UUID | None,
        reason: str = "manual edit",
    ) -> SymbolVersion:
        """Apply an edit and return the version snapshot taken *before* mutation."""
        prior = SymbolVersion(
            symbol_id=self.id,
            version=self.version,
            snapshot=self.snapshot(),
            changed_by=changed_by,
            change_reason=reason,
        )
        if bbox is not None:
            self.bbox = bbox
        if rotation is not None:
            self.rotation = rotation % 360.0
        self.version += 1
        self.updated_at = _now()
        return prior


@dataclass(slots=True)
class Relationship:
    """A directed, typed edge in the symbol graph (adjacency-list model)."""

    document_id: UUID
    source_symbol_id: UUID
    target_symbol_id: UUID
    type: RelationshipType
    confidence: float = 1.0
    properties: dict[str, object] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.source_symbol_id == self.target_symbol_id:
            raise ValueError("A relationship cannot connect a symbol to itself")


@dataclass(slots=True)
class AuditLog:
    actor_id: UUID | None
    entity_type: str
    entity_id: UUID
    action: str
    before: dict[str, object] | None = None
    after: dict[str, object] | None = None
    correlation_id: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)


@dataclass(slots=True)
class User:
    email: str
    password_hash: str
    roles: set[Role] = field(default_factory=lambda: {Role.ENGINEER})
    is_active: bool = True
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def has_role(self, role: Role) -> bool:
        return role in self.roles or Role.ADMIN in self.roles
