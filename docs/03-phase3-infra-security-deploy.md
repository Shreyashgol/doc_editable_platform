# Phase 3 — Infrastructure, Security & Deployment

> Infrastructure Design · Security Design · Deployment Design

---

## 1. Infrastructure Design

### 1.1 Runtime topology

| Service | Scale unit | Stateless? | Notes |
|---------|-----------|-----------|-------|
| `api` (FastAPI/uvicorn-gunicorn) | N replicas behind LB | yes | CPU-light; autoscale on RPS/latency |
| `worker-pdf` | M replicas, queue `pdf` | yes | CPU+memory heavy; cgroup limits (R1) |
| `worker-ocr` | OCR queue | yes | optional GPU; prefetch=1 |
| `worker-classify` | classify queue | yes | rule engine light; ML/ViT heavier |
| `worker-embed` | embed queue | yes | OpenCLIP; batchable; optional GPU |
| `worker-graph` | graph queue | yes | light |
| `beat` | 1 (leader-elected) | no | scheduled cleanup, DLQ sweeps |
| `postgres` (+pgvector) | primary + read replicas | no | system of record |
| `redis` | primary + replica/sentinel | no | broker + result + rate-limit + cache |
| `minio`/S3 | cluster / managed | no | artifacts |
| `clamav` | N replicas | yes | AV daemon for scan port |
| `otel-collector`,`prometheus`,`grafana`,`jaeger` | observability stack | mixed | |

Queues are **separated per worker type** so a slow OCR job can't starve embedding, and each
type autoscales on its own queue depth (R4).

### 1.2 Storage layout (object store)
```
raw/{owner}/{document_id}.pdf
renders/{document_id}/page-{n}.png
crops/{document_id}/page-{n}/{symbol_id}.png
```
Lifecycle: raw PDFs → infrequent-access after 30d; renders/crops regenerable, shorter TTL (R10).

### 1.3 Data lifecycle & scale-out path
- Postgres partitioning of `symbols`/`audit_logs` by document/time when volume warrants.
- pgvector HNSW now → evaluate Qdrant/Milvus behind `SymbolRepository.search_similar` if recall/latency demands.
- Graph stays in Postgres adjacency; `RelationshipRepository` port allows Neo4j adapter later.

---

## 2. Security Design

| Control | Implementation |
|---------|----------------|
| AuthN | JWT access (short TTL) + refresh (rotating), `Authorization: Bearer`; argon2 password hashing |
| AuthZ | RBAC (`admin`,`engineer`,`viewer`) enforced in application services via dependency-injected principal; ownership checks on every document/symbol |
| Rate limiting | Redis token-bucket middleware, per-principal + per-IP, stricter on upload/auth |
| File validation | size cap, MIME allow-list, **magic-byte** sniff (`%PDF-`), filename sanitization |
| PDF validation | structural parse, page-count cap, per-page pixel/stream cap → **PDF-bomb detection** (R1) |
| Virus scanning | **ClamAV** via `VirusScanner` port before any processing; infected → quarantine + `FAILED` |
| Input sanitization | Pydantic strict models, path traversal prevention on storage keys, JSON size limits |
| Secure headers | HSTS, X-Content-Type-Options, X-Frame-Options, CSP, no-sniff, referrer-policy (middleware) |
| Secrets | env/secret-manager only; `.env` gitignored; no secrets in images or logs; redaction in log processor |
| Transport | TLS terminated at LB/ingress; internal mTLS optional |
| Auditing | append-only `audit_logs` with actor + correlation id on every mutating action |
| Least privilege | DB role per service, scoped object-store credentials, network policies between tiers |

**Upload security pipeline (ordered, fail-closed):**
`size check → magic bytes → MIME → structural parse → page/pixel caps → ClamAV → persist`.
Any failure ⇒ reject (422) or quarantine, never proceed to workers.

---

## 3. Deployment Design

### 3.1 Local / CI: `docker-compose`
One command brings up api, all workers, postgres+pgvector, redis, minio, clamav, and the
observability stack. Migrations run as an init job. Seed script creates an admin user + demo doc.

### 3.2 Configuration (Twelve-Factor)
All config via environment, parsed once by a Pydantic `Settings` object. Same image runs in
every environment; only env differs. No environment-specific branches in code.

### 3.3 Production target
- Containers orchestrated by Kubernetes (Helm chart per service) or ECS; HPA on queue depth/RPS.
- Managed Postgres (with pgvector) + managed Redis + S3 in cloud.
- Blue/green or rolling deploys; migrations gated as a pre-deploy job; readiness probes hold
  traffic until DB + broker reachable.
- Secrets via cloud secret manager mounted as env.

### 3.4 CI/CD (GitHub Actions)
`lint (ruff) → type-check (mypy) → unit+integration tests (pytest, coverage gate ≥90%) →
security scan (bandit, pip-audit, trivy image scan) → docker build → push → deploy`.
Frontend pipeline: `eslint → tsc → vitest → build → publish`.

### 3.5 Observability runtime
- **Logs:** structlog JSON to stdout → collector → log store; correlation/request id on every line.
- **Metrics:** Prometheus scrapes `/metrics` (API + workers): request latency, queue depth,
  per-stage duration, success/failure counts, retry counts, DLQ size.
- **Traces:** OpenTelemetry spans across API → broker → worker stages, propagating trace context
  through Celery headers so one document's journey is a single distributed trace.
- **Health:** `/health/live` (process up) and `/health/ready` (DB+Redis+object-store reachable).
- **Alerts:** DLQ size > 0, readiness failing, stage error-rate, p99 latency, vector-search latency.
