"""The worker runtime: claim due tasks, execute the stage handler, and on failure apply
exponential backoff retry or dead-letter the task (and fail the document)."""

from __future__ import annotations

import asyncio
import os
import socket
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...application.unit_of_work import UnitOfWork
from ...core.config import Settings
from ...core.errors import AppError
from ...core.logging import correlation_id_ctx, get_logger
from ...domain.entities import AuditLog, ProcessingJob
from ...domain.value_objects import ClaimedTask
from ...infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from ...infrastructure.queue.postgres_queue import SqlAlchemyTaskQueue
from .engines import WorkerEngines
from .stages import STAGE_HANDLERS

_log = get_logger("worker")
_BACKOFF_CAP_SECONDS = 300.0


class PipelineRunner:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        engines: WorkerEngines,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._engines = engines
        self._worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._stop = asyncio.Event()

    def _uow(self) -> UnitOfWork:
        return SqlAlchemyUnitOfWork(self._session_factory, self._settings)

    async def _claim(self) -> list[ClaimedTask]:
        async with self._session_factory() as session:
            queue = SqlAlchemyTaskQueue(session)
            tasks = await queue.claim_batch(
                self._worker_id,
                limit=self._settings.queue_batch_size,
                visibility_timeout_seconds=self._settings.queue_visibility_timeout_seconds,
            )
            await session.commit()
        return tasks

    async def process_one(self, task: ClaimedTask) -> None:
        cid = str(task.payload.get("correlation_id") or task.document_id)
        token = correlation_id_ctx.set(cid)
        try:
            uow = self._uow()
            try:
                async with uow:
                    handler = STAGE_HANDLERS[task.stage]
                    await handler(uow, self._engines, task)
                    await uow.task_queue.mark_succeeded(task.task_id)
                    await uow.commit()
                _log.info("stage_succeeded", stage=task.stage.value, document_id=str(task.document_id))
            except Exception as exc:  # noqa: BLE001 - convert to retry/dead decision
                await self._handle_failure(task, exc)
        finally:
            correlation_id_ctx.reset(token)

    async def _handle_failure(self, task: ClaimedTask, exc: Exception) -> None:
        retryable = exc.retryable if isinstance(exc, AppError) else True
        will_retry = retryable and task.attempts < task.max_attempts
        _log.warning(
            "stage_failed",
            stage=task.stage.value,
            document_id=str(task.document_id),
            attempt=task.attempts,
            will_retry=will_retry,
            error=str(exc),
        )
        uow = self._uow()
        async with uow:
            if will_retry:
                delay = min(
                    float(self._settings.task_retry_backoff_base_seconds) ** task.attempts,
                    _BACKOFF_CAP_SECONDS,
                )
                await uow.task_queue.mark_retry(
                    task.task_id, error=str(exc), run_after_seconds=delay
                )
            else:
                await uow.task_queue.mark_dead(task.task_id, error=str(exc))
                doc = await uow.documents.get(task.document_id)
                if doc is not None and not doc.status.is_terminal:
                    doc.mark_failed(str(exc))
                    await uow.documents.update(doc)
                job = await uow.documents.get_job(task.document_id) or ProcessingJob(
                    document_id=task.document_id
                )
                job.fail(str(exc))
                await uow.documents.upsert_job(job)
                await uow.audit.add(
                    AuditLog(
                        actor_id=None,
                        entity_type="document",
                        entity_id=task.document_id,
                        action="failed",
                        after={"stage": task.stage.value, "error": str(exc)[:500]},
                    )
                )
            await uow.commit()

    async def reclaim_expired(self) -> int:
        async with self._session_factory() as session:
            queue = SqlAlchemyTaskQueue(session)
            count = await queue.reclaim_expired(
                visibility_timeout_seconds=self._settings.queue_visibility_timeout_seconds
            )
            await session.commit()
            return count

    async def tick(self) -> int:
        """Claim and process one batch. Returns number of tasks processed."""
        tasks = await self._claim()
        for task in tasks:
            await self.process_one(task)
        return len(tasks)

    async def drain(self, *, max_iterations: int = 1000) -> None:
        """Process tasks until the queue is empty. Used by tests to run a pipeline to completion."""
        for _ in range(max_iterations):
            await self.reclaim_expired()
            if await self.tick() == 0:
                return

    async def run_forever(self) -> None:  # pragma: no cover - long-running loop
        _log.info("worker_started", worker_id=self._worker_id)
        idle_ticks = 0
        while not self._stop.is_set():
            processed = await self.tick()
            if idle_ticks % 30 == 0:
                await self.reclaim_expired()
            if processed == 0:
                idle_ticks += 1
                await asyncio.sleep(self._settings.queue_poll_interval_seconds)
            else:
                idle_ticks = 0

    def stop(self) -> None:  # pragma: no cover
        self._stop.set()
