# Phase 1 — Foundations

> Requirements Analysis · Architecture Design · Risk Analysis · Technology Selection · Tradeoff Analysis

This document is the entry point for the **Document AI Platform** — a system that ingests
PDFs of engineering diagrams (P&IDs, schematics, flowcharts) and turns the symbols inside
them into **first-class, editable, searchable domain objects** with metadata, relationships,
and vector embeddings.

The non-negotiable design tenet that drives everything below:

> **A symbol is never "just an image". It is a structured domain entity** with identity,
> geometry, classification, properties, version history, relationships, and an embedding.
> Images (page renders, symbol crops) are *byproducts* stored in object storage and
> referenced by URL.

---

## 1. Requirements Analysis

### 1.1 Functional requirements

| # | Capability | Notes |
|---|------------|-------|
| F1 | Upload PDF | Multipart upload → object storage, dedupe by content hash |
| F2 | Validate PDF | Magic bytes, MIME, size, page count, PDF-bomb heuristics, AV scan |
| F3 | Parse pages | Render pages to raster + extract vector/text layers (PyMuPDF) |
| F4 | Extract symbols | CV pipeline: grayscale → threshold → denoise → contour → segment → bbox |
| F5 | Detect text | OCR per page (PaddleOCR) with confidence + word/line boxes |
| F6 | Associate labels | Nearest-neighbour match of OCR tokens to symbol centroids |
| F7 | Classify symbols | Rule engine (v1) → ML classifier (v2) → ViT (v3) behind one interface |
| F8 | Generate embeddings | OpenCLIP image embedding per symbol crop → pgvector |
| F9 | Store metadata | Symbols, properties, versions, jobs, relationships, audit |
| F10 | Custom properties | Typed key/value properties per symbol, schema-validated |
| F11 | Visual editing | Canvas: move/resize/rotate/zoom/pan/multi-select, persisted as versions |
| F12 | APIs | Versioned REST + OpenAPI for all of the above |
| F13 | AI search / RAG | Vector similarity search now; retrieval-augmented Q&A later |
| F14 | Symbol graph | Directed typed relationships between symbols (`pump --feeds--> valve`) |

### 1.2 Non-functional requirements

| Attribute | Target |
|-----------|--------|
| Scalability | Horizontal scale of stateless API + independently-scalable workers; designed for millions of documents |
| Reliability | Every pipeline stage independently retryable; no data loss on worker crash; DLQ for poison messages |
| Latency | Upload returns < 300 ms (async processing); status polled/streamed |
| Throughput | Bound by worker fleet, not by API; back-pressure via queue |
| Maintainability | Clean Architecture + DDD; business logic isolated from frameworks |
| Security | JWT + RBAC, file validation, AV scan, PDF-bomb detection, secrets management |
| Observability | Structured logs, Prometheus metrics, OpenTelemetry traces, correlation IDs |
| Testability | ≥90% coverage target; domain layer has zero I/O dependencies |
| Extensibility | Pluggable classifier/embedder/extractor; graph store swappable to Neo4j |

### 1.3 Actors & use cases

- **Engineer / Analyst** — uploads drawings, reviews extracted symbols, edits, searches.
- **Reviewer / Approver** — validates classifications, adds custom properties.
- **Admin** — manages users/roles, quotas, retention.
- **System (workers)** — autonomous pipeline actors reacting to events.
- **Downstream AI services** — consume embeddings & graph for RAG (future).

### 1.4 Explicit non-goals (v1)

- Real-time collaborative editing (CRDT) — single-writer optimistic versioning only.
- Full Neo4j deployment — graph lives in Postgres with a **port** designed for later migration.
- Training custom CV/ML models — v1 ships the rule engine + pretrained OpenCLIP; ML/ViT are
  pluggable strategies stubbed behind interfaces.

---

## 2. Architecture Design

### 2.1 Style: Clean Architecture + DDD, event-driven processing

```
            ┌────────────────────────────────────────────────────────┐
            │                     React Frontend                      │
            │  Upload · Dashboard · Canvas · Property · Graph · Search │
            └───────────────────────────┬────────────────────────────┘
                                         │ HTTPS / JSON (versioned REST)
            ┌───────────────────────────▼────────────────────────────┐
            │                FastAPI API Gateway (stateless)          │
            │  AuthN/Z · validation · rate limit · OpenAPI · DI wiring │
            └───────┬───────────────────────────────────┬────────────┘
                    │ enqueue                            │ read/write
            ┌───────▼─────────┐                 ┌────────▼───────────┐
            │  Redis  (broker │                 │ PostgreSQL+pgvector│
            │  + result + DLQ)│                 │ metadata · vectors │
            └───────┬─────────┘                 │ graph · audit      │
                    │ consume                    └────────┬───────────┘
        ┌───────────▼──────────────────────────────┐     │ refs/URLs
        │             Celery Worker Pipeline        │     │
        │  pdf → ocr → classify → embed → graph     ├─────┘
        └───────────┬──────────────────────────────┘
                    │ put/get objects
            ┌───────▼─────────┐
            │  MinIO / S3     │  raw PDFs · page renders · symbol crops
            └─────────────────┘
```

### 2.2 Layering (per deployable: `api` and `worker` share the same package)

```
backend/app/
├── domain/          # Pure: entities, value objects, enums, domain events, ports (interfaces)
│                    #   NO imports of FastAPI/SQLAlchemy/Celery. Unit-testable in isolation.
├── application/     # Use cases / services orchestrating domain + ports. Transaction script
│                    #   boundaries live here. Depends on domain only (via interfaces).
├── infrastructure/  # Adapters: SQLAlchemy repos, Redis/Celery, MinIO, OCR/CV/CLIP engines.
│                    #   Implements ports defined in domain. The only place frameworks live.
├── interfaces/      # Delivery: FastAPI routers (thin), Celery task entrypoints, schemas (DTO).
└── core/            # Cross-cutting: config, DI container, logging, telemetry, errors, security.
```

**Dependency rule:** source dependencies point *inward only*.
`interfaces → application → domain` and `infrastructure → domain`. The domain depends on
nothing. Wiring happens at the composition root (`core/container.py`).

### 2.3 Why thin controllers / no business logic in routes

Routers do exactly three things: (1) parse & validate the request into a DTO, (2) call a
single application service method, (3) serialize the result. This keeps delivery swappable
(REST today, gRPC/GraphQL later) and keeps use cases unit-testable without HTTP.

### 2.4 Processing model

The API never does CPU-heavy work. Upload persists the file + a `Document` row in state
`UPLOADED` and emits a domain event. A chain of Celery tasks advances the document through
the state machine, each task idempotent and independently retryable. State, transitions,
timestamps, and audit entries are persisted so the pipeline is fully observable and resumable.

---

## 3. Risk Analysis

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|-----------|--------|------------|
| R1 | **PDF bombs / decompression bombs** crash workers | Med | High | Pre-validation: page-count cap, per-page pixel cap, stream size cap, render timeout, sandboxed worker with memory cgroup limit |
| R2 | **Malicious PDF / embedded payloads** | Med | High | Magic-byte + structural validation, ClamAV scan before processing, no JS execution, render in isolated worker |
| R3 | **OCR/CV accuracy is domain-specific** and low on noisy scans | High | Med | Confidence thresholds, human-in-the-loop editing UI, pluggable engines, store provenance so re-runs are cheap |
| R4 | **Long-running CV/OCR blocks queue** | Med | Med | Per-task soft/hard time limits, separate queues per worker type, autoscaling, prefetch=1 for heavy tasks |
| R5 | **Poison messages** loop forever | Med | Med | Bounded retries w/ exponential backoff → Dead Letter Queue + `FAILED` state + alert |
| R6 | **Vector index growth** degrades search | Med | Med | pgvector HNSW index, dimensionality fixed by model, partitioning/ANN tuning, roadmap to dedicated vector DB |
| R7 | **Schema evolution** breaks consumers | Med | Med | Versioned APIs, Alembic migrations, additive-first changes, contract tests |
| R8 | **Lost work on crash mid-stage** | Med | High | Idempotent stages keyed by (document, stage); object storage is source of truth for artifacts; transactional outbox for events |
| R9 | **Secret leakage** | Low | High | Secrets via env/secret manager, never in code/images, `.env` gitignored, rotation policy |
| R10 | **Cost blowout** at millions of docs | Med | Med | Tiered storage lifecycle, embedding/crop dedupe by perceptual hash, batch embedding, async everything |
| R11 | **Tight coupling to Postgres for graph** | Low | Med | Graph behind a `GraphRepository` port; Postgres adapter now, Neo4j adapter later, no domain change |

See `docs/adr/` for the decisions that resolve the highest-impact risks.

---

## 4. Technology Selection

| Concern | Choice | Why (vs. alternatives) |
|---------|--------|------------------------|
| API framework | **FastAPI** | Async, Pydantic v2 validation, first-class OpenAPI. vs Flask (no async/validation), Django (heavy, ORM-coupled) |
| ORM | **SQLAlchemy 2.0 + Alembic** | Mature, async support, explicit unit-of-work, migrations. vs raw asyncpg (no UoW), Tortoise (smaller ecosystem) |
| Validation | **Pydantic v2** | Fast (Rust core), shared DTO/runtime validation |
| DB | **PostgreSQL + pgvector** | One store for relational + vector + JSONB props + recursive graph queries. vs separate vector DB (operational overhead at this stage) |
| Queue | **Redis + Celery** | Proven task orchestration, retries, routing, beat. vs RabbitMQ (heavier), Arq/Dramatiq (smaller). Redis also serves rate-limit + cache |
| Object storage | **MinIO (S3 API)** | S3-compatible, runs locally and in cloud unchanged. Swap to AWS S3 in prod via config only |
| PDF | **PyMuPDF (fitz)** | Fast render + text/vector extraction + per-page control for bomb limits |
| CV | **OpenCV** | Industry-standard contour/threshold/morphology ops |
| OCR | **PaddleOCR** | Strong on rotated/technical text, angle classifier, box output |
| Embeddings | **OpenCLIP** | Pretrained joint image/text space → enables text→symbol search & RAG |
| Frontend | **React + TS + React Query + Zustand + React Konva** | Konva = performant 2D canvas for symbol editing; RQ for server state; Zustand for canvas UI state |
| Observability | **structlog + Prometheus + OpenTelemetry** | Structured JSON logs, metrics, distributed traces with correlation IDs |
| Testing | **Pytest + FactoryBoy** | Fixtures, parametrization, deterministic factories |

### 4.1 Trade-off: Postgres-for-everything (v1) vs. polyglot persistence

We deliberately start with **Postgres + pgvector** as the single system of record (relational,
JSONB properties, vector, and graph via adjacency + recursive CTE). This minimizes operational
surface while we validate the product. Every boundary that *might* later demand a specialized
store (vectors → Milvus/Qdrant; graph → Neo4j) is hidden behind a **port interface**, so the
migration is an adapter swap, not a rewrite.

### 4.2 Trade-off: Celery vs. a custom event bus

Celery gives retries, routing, scheduling, and a result backend for free. The cost is Celery's
opinionated model. We isolate it: domain emits **domain events**; an infrastructure adapter maps
events → Celery tasks. The domain never imports Celery, so we can move to Kafka/NATS later.

---

## 5. Tradeoff Analysis Summary

| Decision | Chosen | Rejected alternative | Trade accepted |
|----------|--------|----------------------|----------------|
| Sync vs async processing | Async (queue) | Inline request processing | Eventual consistency + status polling, for throughput & resilience |
| Mono-store vs polyglot | Postgres+pgvector | Dedicated vector + graph DBs | Some ceiling on scale, bought simplicity + ports for later |
| Rule engine first | Deterministic rules | Train ML model up front | Lower recall on unseen symbols, bought explainability + speed to value |
| Strong layering | Clean/DDD | Pragmatic 2-layer CRUD | More files/indirection, bought testability + extensibility |
| Optimistic versioning | Version rows | Real-time CRDT | No live co-edit in v1, bought simplicity + full audit history |

**Bottom line:** v1 optimizes for *correct structure and clean seams* so the hard parts
(better models, specialized stores, RAG) plug in without architectural change.
