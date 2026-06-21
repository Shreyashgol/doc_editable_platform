"""Domain events.

Events are immutable facts about something that happened. The application layer raises them;
an infrastructure ``EventPublisher`` adapter maps them onto the Celery pipeline. The domain
never knows a broker exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Base event. Carries an id, timestamp, and correlation id for tracing."""

    aggregate_id: UUID
    correlation_id: str | None = None
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def name(self) -> str:
        return type(self).__name__


@dataclass(frozen=True, slots=True)
class DocumentUploaded(DomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class DocumentValidated(DomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class DocumentRejected(DomainEvent):
    reason: str = ""


@dataclass(frozen=True, slots=True)
class PagesExtracted(DomainEvent):
    page_count: int = 0


@dataclass(frozen=True, slots=True)
class SymbolsDetected(DomainEvent):
    symbol_count: int = 0


@dataclass(frozen=True, slots=True)
class TextExtracted(DomainEvent):
    token_count: int = 0


@dataclass(frozen=True, slots=True)
class LabelsAssociated(DomainEvent):
    associated_count: int = 0


@dataclass(frozen=True, slots=True)
class SymbolsClassified(DomainEvent):
    classified_count: int = 0


@dataclass(frozen=True, slots=True)
class EmbeddingsGenerated(DomainEvent):
    embedded_count: int = 0


@dataclass(frozen=True, slots=True)
class RelationshipsInferred(DomainEvent):
    edge_count: int = 0


@dataclass(frozen=True, slots=True)
class DocumentCompleted(DomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class DocumentFailed(DomainEvent):
    stage: str = ""
    reason: str = ""
