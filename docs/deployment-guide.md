# Deployment Guide

## Local (one command)
```bash
cp backend/.env.example backend/.env      # adjust secrets
docker compose -f infra/docker-compose.yml up --build
```
This starts: Postgres+pgvector, MinIO (+bucket), ClamAV, a migration job, the API, two worker
replicas, Prometheus, and Grafana. The API is on `http://localhost:8000` (`/docs` for OpenAPI).
There is **no Redis/Celery** — the job queue is the `pipeline_tasks` Postgres table (ADR 0005).

Create an admin user:
```bash
docker compose -f infra/docker-compose.yml run --rm api python -m scripts.seed
```

### Using Neon instead of local Postgres
Set `APP_DATABASE_URL` / `APP_DATABASE_SYNC_URL` to your Neon URLs and `APP_DB_REQUIRE_SSL=true`
in `.env`. Use the **async** URL with `+asyncpg` (SSL + statement cache disabled for the pooled
endpoint is handled in `db/base.py`) and the **sync** URL with `+psycopg` and `?sslmode=require`
for Alembic. You can then remove the `postgres` service from compose.

## Running components without Docker
```bash
cd backend && python -m venv .venv && . .venv/bin/activate
pip install ".[ml,dev]"                 # omit ml for the lightweight (hash/no-OCR) backends
alembic upgrade head
uvicorn app.main:app --reload           # API
python -m app.interfaces.worker.run     # worker (separate process; scale by running more)
```

## Configuration (Twelve-Factor)
All config is environment variables (`APP_` prefix), parsed once by `core/config.py`. Key knobs:

| Var | Purpose |
|-----|---------|
| `APP_JWT_SECRET` | **must** be set in production (validated) |
| `APP_DATABASE_URL` / `APP_DATABASE_SYNC_URL` | async (app) / sync (migrations) DB URLs |
| `APP_DB_REQUIRE_SSL` | `true` for Neon/managed Postgres |
| `APP_S3_*` | object storage (MinIO/S3) endpoint + credentials + bucket |
| `APP_CLAMAV_ENABLED` / `APP_CLAMAV_HOST` | virus scanning |
| `APP_OCR_BACKEND` | `none` (default) or `paddle` (needs ml extra) |
| `APP_EMBEDDING_BACKEND` | `hash` (default) or `openclip` (needs ml extra) |
| `APP_WORKER_CONCURRENCY`, `APP_QUEUE_*`, `APP_TASK_*` | worker/queue tuning |

> The embedding backend **must be the same** for the worker (writes vectors) and the API
> (search query vectors) or similarity is meaningless.

## Migrations
`alembic upgrade head` is idempotent and gated as a pre-deploy job (compose `migrate` service /
CI step). Roll back with `alembic downgrade -1`. Make schema changes additive-first.

## Production topology
- Stateless `api` behind a load balancer; autoscale on RPS/latency. TLS at the ingress.
- `worker` deployment scaled independently (autoscale on `pipeline_tasks` pending depth). Each
  worker claims disjoint tasks via `FOR UPDATE SKIP LOCKED`, so adding replicas just adds
  throughput. Set per-type concurrency via replicas/env.
- Managed Postgres (with pgvector) + S3 + a ClamAV deployment. Secrets via the platform secret
  manager mounted as env. Readiness probe (`/health/ready`) gates traffic until DB is reachable.
- Run `alembic upgrade head` as a pre-deploy job; deploy API/worker with rolling or blue/green.

## Scaling notes
- Vector search: HNSW index already present; tune `ef_search`, consider partitioning `symbols`
  by document, or move vectors behind `SymbolRepository.search_similar` to Qdrant/Milvus.
- Graph: adjacency + recursive CTE today; the `RelationshipRepository` port allows a Neo4j
  adapter without domain changes.
- Object lifecycle: move raw PDFs to infrequent-access after 30d; renders/crops are regenerable.
