# Document AI Platform

Production-grade platform that ingests PDFs of engineering diagrams (P&IDs, schematics,
flowcharts, industrial process diagrams) and turns the symbols inside them into **first-class,
editable, searchable domain objects** — with metadata, custom properties, version history,
a relationship graph, and vector embeddings for AI search and future RAG.

> **Core principle:** a symbol is never stored as "just an image". It is a structured domain
> entity (`id, type, label, page, bbox, rotation, properties, embedding`). Image artifacts live
> in object storage and are referenced by URL.

```
PDF → Extracted Symbols → Structured Objects → Editable Properties → Searchable Knowledge Base
```

## Architecture at a glance

```
React (Konva canvas) → FastAPI gateway → Postgres-backed job queue (FOR UPDATE SKIP LOCKED)
        → Worker pipeline (validate → pdf → ocr → classify → embed → graph)
        → PostgreSQL + pgvector  ·  MinIO/S3 object storage
```

> The async pipeline runs on a **durable Postgres job queue** (no Redis/Celery) — see
> [ADR 0005](docs/adr/0005-postgres-job-queue-supersedes-celery.md), which supersedes ADR 0003.

Built on Clean Architecture + DDD: a framework-free **domain** core, **application** use cases,
**infrastructure** adapters behind ports, and thin **interfaces** (HTTP + workers).

## Documentation (read in order)

| Phase | Document |
|-------|----------|
| 1 — Foundations | [`docs/01-phase1-foundations.md`](docs/01-phase1-foundations.md) — requirements, architecture, risk, tech selection, tradeoffs |
| 2 — Data/API/Domain | [`docs/02-phase2-data-api-domain.md`](docs/02-phase2-data-api-domain.md) — domain model, state machine, events, DB schema, API spec |
| 3 — Infra/Security/Deploy | [`docs/03-phase3-infra-security-deploy.md`](docs/03-phase3-infra-security-deploy.md) |
| 4 — Implementation Plan | [`docs/04-phase4-implementation-plan.md`](docs/04-phase4-implementation-plan.md) |
| ADRs | [`docs/adr/`](docs/adr/) — key decisions with alternatives & tradeoffs |

## Status

Phases 1–4 (design) are complete and committed. Phase 5 (production code) is built in the
milestone order defined in the implementation plan (M0 scaffolding → M7 docs). See that document
for the current milestone and exit criteria.

## Tech stack

Python 3.12 · FastAPI · SQLAlchemy 2.0 · Alembic · Pydantic v2 · PostgreSQL + pgvector ·
**Postgres-backed durable job queue** (no Redis/Celery) · MinIO/S3 · PyMuPDF · OpenCV · PaddleOCR · OpenCLIP ·
React + TypeScript + React Query + Zustand + React Konva ·
structlog · Prometheus · OpenTelemetry · Pytest · FactoryBoy.
