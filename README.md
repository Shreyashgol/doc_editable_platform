# Document AI Platform

Production-grade platform that ingests PDFs of engineering diagrams (P&IDs, schematics,
flowcharts, industrial process diagrams) and turns the symbols inside them into **first-class,
editable, searchable domain objects** — with metadata, custom properties, version history,
relationship graph, and vector embeddings for AI search and future RAG.

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
| Guides | [deployment](docs/deployment-guide.md) · [monitoring](docs/monitoring-guide.md) · [security](docs/security-guide.md) |

## Layout

```
backend/    FastAPI app + worker (Clean Architecture: domain / application / infrastructure / interfaces)
frontend/   React + TS SPA (upload, dashboard, Konva canvas, graph, search)
infra/      docker-compose (Postgres+pgvector, MinIO, ClamAV, Prometheus, Grafana) + configs
docs/       Phase 1–4 design, ADRs, operational guides
.github/    CI (lint, type-check, security scan, tests+coverage gate, docker build+scan)
```

Run the whole stack: `docker compose -f infra/docker-compose.yml up --build` (see the
[deployment guide](docs/deployment-guide.md)). Backend tests run against Postgres/pgvector
(local container or Neon); the suite enforces a 90% coverage gate.

## Status

Phases 1–4 (design) and Phase 5 (production code) are complete:

| Milestone | Scope | Verified |
|-----------|-------|----------|
| M0 | Scaffold + framework-free domain (entities, state machine, value objects, ports) | domain unit tests |
| M1 | SQLAlchemy models, Alembic + pgvector, repositories | integration tests on live Postgres |
| M2 | Auth (JWT+RBAC), upload validation pipeline, Postgres job queue, middleware | API tests |
| M3 | Worker pipeline: validate→extract→OCR→classify→embed→graph→finalize | end-to-end pipeline test (real PyMuPDF+OpenCV) |
| M4 | Symbol/property/version/graph/search APIs | API tests |
| M5 | React frontend (upload, dashboard, Konva canvas, graph, search) | vitest store tests |
| M6 | Prometheus/structlog/health, rate limiting, ClamAV, docker-compose, CI/CD, guides | — |

Tests exercise real Postgres + pgvector and real CV extraction; the suite enforces a 90%
coverage gate in CI.

## Tech stack

Python 3.12 · FastAPI · SQLAlchemy 2.0 · Alembic · Pydantic v2 · PostgreSQL + pgvector ·
**Postgres-backed durable job queue** (no Redis/Celery) · MinIO/S3 · PyMuPDF · OpenCV · PaddleOCR · OpenCLIP ·
React + TypeScript + React Query + Zustand + React Konva ·
structlog · Prometheus · OpenTelemetry · Pytest · FactoryBoy.
