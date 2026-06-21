# Phase 4 — Implementation Plan

> The ordered, dependency-aware plan that Phase 5 (code) executes against.
> Each milestone is independently shippable and testable.

## Repository layout (target)

```
techrusk-assignment/
├── docs/                          # Phases 1–4 (this set) + ADRs + guides
│   ├── adr/                       # Architecture Decision Records
│   ├── deployment-guide.md
│   ├── monitoring-guide.md
│   └── security-guide.md
├── backend/
│   ├── app/
│   │   ├── domain/                # entities, value objects, enums, events, ports
│   │   ├── application/           # use-case services
│   │   ├── infrastructure/        # db, storage, queue, cv, ocr, embeddings, security adapters
│   │   ├── interfaces/            # http routers + schemas, worker tasks
│   │   └── core/                  # config, container, logging, telemetry, errors, security
│   ├── migrations/                # Alembic
│   ├── tests/                     # unit / integration / api / worker
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/                 # Upload, Dashboard, Canvas, PropertyEditor, Graph, Search
│   │   ├── components/
│   │   ├── api/                   # React Query hooks + typed client
│   │   ├── store/                 # Zustand canvas state
│   │   └── types/
│   ├── package.json
│   └── Dockerfile
├── infra/
│   ├── docker-compose.yml
│   ├── prometheus/ grafana/ otel/ # observability configs
│   └── init/                      # db init, minio bucket bootstrap
├── .github/workflows/             # ci.yml
└── README.md
```

## Milestones

### M0 — Scaffolding & contracts  *(foundation)*
- `pyproject.toml`, tooling (ruff, mypy, pytest), `core/config.py`, `core/errors.py`.
- Domain enums + value objects + entity skeletons + **all port interfaces**.
- Pydantic DTOs for API. OpenAPI generates from these.
- **Exit:** `pytest` runs; domain unit tests for value objects (bbox math, state machine) pass.

### M1 — Persistence & migrations
- SQLAlchemy models mirroring Phase 2 schema; Alembic baseline migration; pgvector extension.
- Repository adapters (Document, Symbol, Relationship, Audit) implementing domain ports.
- **Exit:** repository integration tests (against ephemeral Postgres) pass.

### M2 — API gateway (upload → status)
- Auth (JWT+RBAC), upload endpoint with full validation pipeline, status/list/detail.
- DI container wiring; global exception middleware; correlation-id + secure-headers middleware.
- **Exit:** API tests cover upload happy path + every validation rejection.

### M3 — Worker pipeline
- Celery app, queue routing, base task (idempotency, retry/backoff, DLQ, telemetry).
- Stages: pdf-extract (PyMuPDF render + OpenCV `extract_symbols`), ocr (PaddleOCR `extract_text`
  + `associate_text_to_symbol`), classify (rule engine), embed (OpenCLIP), graph build.
- State-machine advancement + audit on every transition (transactional outbox).
- **Exit:** worker tests with fakes per stage; one end-to-end pipeline test on a sample PDF.

### M4 — Symbols, properties, versions, graph, search APIs
- Symbol edit (→ version), typed properties upsert, graph read/write, similarity search.
- **Exit:** API + integration tests for each.

### M5 — Frontend
- Typed API client + React Query hooks; Upload, Dashboard (live status), Canvas (Konva:
  drag/resize/rotate/zoom/pan/multi-select), Property Editor, Graph Viewer, Search.
- **Exit:** component tests (vitest) + a Cypress/Playwright smoke for upload→canvas.

### M6 — Observability, security hardening, CI/CD
- structlog/Prometheus/OTel wiring, health checks; rate limiting; ClamAV adapter; bandit/trivy.
- GitHub Actions pipeline with coverage gate.
- **Exit:** CI green; `docker-compose up` yields a working end-to-end demo.

### M7 — Docs & guides
- Deployment guide, monitoring guide, security guide, ADRs finalized, API spec exported.

## Testing strategy (≥90% target)
- **Domain:** pure unit tests, no I/O (state machine, bbox/iou, label association, rule engine).
- **Application:** use-case tests with fake ports.
- **Infrastructure:** integration tests against real Postgres/Redis/MinIO via compose/testcontainers.
- **API:** httpx AsyncClient against app with overridden DI providing fakes/test DB.
- **Worker:** task tests with fake engines + one slow E2E marked `@pytest.mark.e2e`.
- **CV/OCR:** deterministic fixtures (small synthetic PNGs with known shapes/text).
- FactoryBoy factories for all entities; coverage enforced in CI.

## Build order rationale
Contracts (ports/DTOs) first means every later layer codes against stable interfaces and is
testable with fakes immediately — no layer waits on another's implementation, and the 90%
coverage target is reachable because the domain has zero I/O to mock.
