"""Postgres-backed durable job queue (ADR 0005).

Claiming uses ``FOR UPDATE SKIP LOCKED`` so N workers pull disjoint batches without blocking
each other. Enqueue is idempotent per (document, stage): a conflicting insert resets the row to
pending, which makes re-runs and the transactional outbox safe.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.enums import ProcessingStage
from ...domain.ports import TaskQueue
from ...domain.value_objects import ClaimedTask


class SqlAlchemyTaskQueue(TaskQueue):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(
        self,
        document_id: UUID,
        stage: ProcessingStage,
        *,
        max_attempts: int,
        run_after_seconds: float = 0.0,
        payload: dict[str, object] | None = None,
    ) -> None:
        import json

        await self._session.execute(
            text(
                """
                INSERT INTO pipeline_tasks
                    (id, document_id, stage, status, attempts, max_attempts,
                     run_after, payload, created_at, updated_at)
                VALUES
                    (gen_random_uuid(), :doc, :stage, 'pending', 0, :max_attempts,
                     now() + make_interval(secs => :delay), CAST(:payload AS jsonb), now(), now())
                ON CONFLICT (document_id, stage) DO UPDATE
                    SET status = 'pending',
                        run_after = now() + make_interval(secs => :delay),
                        attempts = 0,
                        locked_at = NULL,
                        locked_by = NULL,
                        last_error = NULL,
                        updated_at = now()
                """
            ),
            {
                "doc": str(document_id),
                "stage": stage.value,
                "max_attempts": max_attempts,
                "delay": float(run_after_seconds),
                "payload": json.dumps(payload or {}),
            },
        )

    async def claim_batch(
        self, worker_id: str, *, limit: int, visibility_timeout_seconds: int
    ) -> list[ClaimedTask]:
        rows = (
            await self._session.execute(
                text(
                    """
                    WITH due AS (
                        SELECT id FROM pipeline_tasks
                        WHERE status = 'pending' AND run_after <= now()
                        ORDER BY run_after
                        FOR UPDATE SKIP LOCKED
                        LIMIT :limit
                    )
                    UPDATE pipeline_tasks t
                    SET status = 'running',
                        attempts = t.attempts + 1,
                        locked_at = now(),
                        locked_by = :worker
                    FROM due
                    WHERE t.id = due.id
                    RETURNING t.id, t.document_id, t.stage, t.attempts, t.max_attempts, t.payload
                    """
                ),
                {"limit": limit, "worker": worker_id},
            )
        ).all()
        return [
            ClaimedTask(
                task_id=r.id,
                document_id=r.document_id,
                stage=ProcessingStage(r.stage),
                attempts=r.attempts,
                max_attempts=r.max_attempts,
                payload=dict(r.payload or {}),
            )
            for r in rows
        ]

    async def mark_succeeded(self, task_id: UUID) -> None:
        await self._session.execute(
            text(
                "UPDATE pipeline_tasks SET status='succeeded', locked_at=NULL, locked_by=NULL, "
                "last_error=NULL WHERE id = :id"
            ),
            {"id": str(task_id)},
        )

    async def mark_retry(self, task_id: UUID, *, error: str, run_after_seconds: float) -> None:
        await self._session.execute(
            text(
                """
                UPDATE pipeline_tasks
                SET status='pending', locked_at=NULL, locked_by=NULL, last_error=:err,
                    run_after = now() + make_interval(secs => :delay)
                WHERE id = :id
                """
            ),
            {"id": str(task_id), "err": error[:2000], "delay": float(run_after_seconds)},
        )

    async def mark_dead(self, task_id: UUID, *, error: str) -> None:
        await self._session.execute(
            text(
                "UPDATE pipeline_tasks SET status='dead', locked_at=NULL, locked_by=NULL, "
                "last_error=:err WHERE id = :id"
            ),
            {"id": str(task_id), "err": error[:2000]},
        )

    async def reclaim_expired(self, *, visibility_timeout_seconds: int) -> int:
        result = await self._session.execute(
            text(
                """
                UPDATE pipeline_tasks
                SET status='pending', locked_at=NULL, locked_by=NULL,
                    last_error='lease expired; reclaimed'
                WHERE status='running'
                  AND locked_at < now() - make_interval(secs => :ttl)
                """
            ),
            {"ttl": visibility_timeout_seconds},
        )
        return result.rowcount or 0
