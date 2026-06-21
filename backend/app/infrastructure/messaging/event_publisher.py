"""EventPublisher adapters.

The Postgres adapter translates domain events into queue tasks (transactional outbox: it runs
in the request's session/transaction, so a committed Document always has its first task and a
rolled-back upload leaves no orphan task). The collecting adapter is a test double.
"""

from __future__ import annotations

from ...domain.enums import ProcessingStage
from ...domain.events import DocumentUploaded, DomainEvent
from ...domain.ports import EventPublisher, TaskQueue


class PostgresEventPublisher(EventPublisher):
    def __init__(self, task_queue: TaskQueue, *, max_attempts: int) -> None:
        self._queue = task_queue
        self._max_attempts = max_attempts

    async def publish(self, event: DomainEvent) -> None:
        # The API only emits the pipeline's first event; the worker chains subsequent stages
        # directly via the queue, so only DocumentUploaded needs translation here.
        if isinstance(event, DocumentUploaded):
            await self._queue.enqueue(
                event.aggregate_id,
                ProcessingStage.VALIDATE,
                max_attempts=self._max_attempts,
                payload={"correlation_id": event.correlation_id or ""},
            )


class CollectingEventPublisher(EventPublisher):
    """Captures events in memory for assertions in tests."""

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self.events.append(event)
