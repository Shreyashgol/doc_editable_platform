# ADR 0005 — Postgres-backed job queue instead of Redis/Celery

- **Status:** Accepted — **supersedes ADR 0003**
- **Date:** 2026-06-20

## Context
ADR 0003 chose Redis + Celery for the async pipeline. A constraint was subsequently imposed:
**do not use Redis or Celery.** We still require everything the pipeline promised: processing
off the request path, independent per-stage retryability, exponential backoff, a dead-letter
path, idempotency, crash recovery, and the document state machine.

We already operate PostgreSQL (Neon) as the system of record.

## Decision
Use **PostgreSQL as the durable job queue**. A `pipeline_tasks` table holds one row per
(document, stage) unit of work. A standalone **worker process** polls for due tasks and claims
them atomically with:

```sql
SELECT ... FROM pipeline_tasks
WHERE status = 'pending' AND run_after <= now()
ORDER BY run_after
FOR UPDATE SKIP LOCKED
LIMIT :batch
```

`FOR UPDATE SKIP LOCKED` lets many workers pull disjoint tasks concurrently without contention.
Each task carries `attempts`, `max_attempts`, `run_after`, `locked_at`, and `locked_by`.
- **Success** → mark `succeeded`, enqueue the next stage's task in the same transaction.
- **Retryable failure** → `attempts++`, set `run_after = now() + base^attempts` (capped) → `pending`.
- **Exhausted / non-retryable** → `status = 'dead'` (dead-letter), document → `FAILED`, alert.
- **Crash recovery** → a sweeper reclaims rows whose lease (`locked_at + visibility_timeout`)
  has expired.

The domain still emits **domain events**; the `EventPublisher` port is implemented by a
`PostgresTaskEnqueuer` adapter that inserts task rows. The domain is unchanged and unaware of
the transport — exactly the seam ADR 0003 relied on, so this is an adapter swap.

Rate limiting moves to an in-process limiter (per replica). This is a known weakening vs. a
shared Redis limiter; documented and acceptable, and can be backed by a Postgres counter if
strict global limits are later required.

## Consequences
- (+) **Zero extra infrastructure** — one datastore to run, back up, and reason about.
- (+) **Stronger durability** — tasks are transactional with the state change (true outbox); no
  "committed work but lost the broker message" window.
- (+) Retries/backoff/DLQ/idempotency all preserved; visibility-timeout gives crash recovery.
- (−) Throughput ceiling is Postgres, not a dedicated broker; mitigated by SKIP LOCKED batching,
  per-stage indexing, and the option to partition the queue table. For millions of documents
  this is comfortable; if it ever isn't, the `EventPublisher` port allows a broker adapter.
- (−) Polling adds small latency (sub-second at the configured interval) vs. push delivery.
- (−) Rate limiting is per-replica unless backed by Postgres.

## Alternatives
- **FastAPI BackgroundTasks:** couples the worker to the API process; no durability, retries, or
  independent scaling. Rejected.
- **Reintroduce a broker (RabbitMQ/NATS):** violates the "no extra infra" intent here and adds
  an operational component we explicitly want to avoid. Deferred behind the port.
