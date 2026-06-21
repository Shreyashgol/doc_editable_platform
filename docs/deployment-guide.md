# Deployment Guide

The platform is designed to run as a **single-datastore** system: one Neon Postgres holds
metadata, the durable job queue, vectors, the graph, audit, **and object blobs**. That makes a
fully-free deploy possible with no Redis, no MinIO/S3, and no paid background worker.

| Component | Host | Role |
|-----------|------|------|
| Database + queue + blobs | **Neon** Postgres (pgvector) | the only stateful dependency |
| API **+ in-process worker** | **Render** web service | serves the API and processes uploads |
| Frontend SPA | **Vercel** | static build, calls the API |

---

## 1. Database — Neon
1. Create a Neon project (free tier). Neon ships with `pgvector`.
2. Copy two connection strings (same DB, two drivers):
   - **async** (app): `postgresql+asyncpg://USER:PASS@HOST/neondb`
   - **sync** (migrations): `postgresql+psycopg://USER:PASS@HOST/neondb?sslmode=require`
3. Migrations run automatically on deploy (pre-deploy command) — or once from the Render Shell:
   `alembic upgrade head`.

---

## 2. Backend — Render (single free web service)

Create a **Web Service** from the repo (or use the included `render.yaml` Blueprint).

**Build / runtime settings**
| Field | Value |
|-------|-------|
| Runtime | Docker |
| Root Directory | `backend` |
| Docker Build Context Directory | `.` (→ `backend/`) |
| Dockerfile Path | `Dockerfile` (→ `backend/Dockerfile`) |
| Docker Command | *(leave empty — the Dockerfile binds `$PORT`)* |
| Health Check Path | `/health/ready` |
| Pre-Deploy Command | `alembic upgrade head` |

> The Dockerfile's `CMD` binds `0.0.0.0:${PORT}` in shell form, so Render's injected `$PORT`
> resolves automatically — no dashboard command needed.

**Environment variables**
```
APP_ENVIRONMENT=production
APP_RUN_WORKER_IN_PROCESS=true        # one service runs API + pipeline (no paid worker)
APP_OBJECT_STORE_BACKEND=postgres     # blobs in Neon — no object store to provision
APP_DB_REQUIRE_SSL=true
APP_OCR_BACKEND=none                  # default; "paddle" needs an ML image
APP_EMBEDDING_BACKEND=hash            # default; "openclip" needs an ML image
APP_JWT_SECRET=<a long random secret>
APP_DATABASE_URL=postgresql+asyncpg://…neon.tech/neondb
APP_DATABASE_SYNC_URL=postgresql+psycopg://…neon.tech/neondb?sslmode=require
APP_CORS_ALLOW_ORIGINS=https://<your-vercel-url>   # set after the frontend deploys
```

Deploy → logs should show `Listening at: http://0.0.0.0:<port>` then
`in_process_worker_starting`. Verify:
```bash
curl -s https://<your-api>.onrender.com/health/ready    # {"status":"ok","checks":{"database":"ok"}}
```
Seed an admin from the **Shell** tab: `python -m scripts.seed`.

### Scaling out (optional, paid)
For independent scaling, set `APP_RUN_WORKER_IN_PROCESS=false` on the web service and add a
**Background Worker** service (same repo/image) with Docker Command
`python -m app.interfaces.worker.run` and the same env vars. The Postgres queue uses
`FOR UPDATE SKIP LOCKED`, so any number of workers/replicas safely share the work.

---

## 3. Frontend — Vercel
1. Import the repo. **Root Directory:** `frontend` (Vite auto-detected; `vercel.json` sets the
   build and SPA fallback).
2. **Environment Variable:** `VITE_API_BASE_URL = https://<your-api>.onrender.com`
3. Deploy → note the URL.
4. Back on Render, set `APP_CORS_ALLOW_ORIGINS` to the Vercel URL (comma-separate multiples) and
   redeploy the API.

---

## 4. Verify end-to-end
Open the Vercel URL → register → log in → upload a PDF → watch the dashboard status walk
`UPLOADED → … → COMPLETED`, then open the canvas, edit a symbol, and try search.

---

## Switching object storage to S3 (for scale)
Postgres blobs are ideal for a single-service deploy but not for millions of documents. To use
object storage instead, set on **both** API and worker:
```
APP_OBJECT_STORE_BACKEND=s3
APP_S3_ENDPOINT_URL=…      # MinIO http://…:9000 | S3 https://s3.amazonaws.com | GCS https://storage.googleapis.com | R2 https://<acct>.r2.cloudflarestorage.com
APP_S3_ACCESS_KEY=…
APP_S3_SECRET_KEY=…
APP_S3_BUCKET=documents
APP_S3_REGION=…
APP_S3_USE_SSL=true
```
Pre-create the bucket in the provider console. The adapter uses SigV4 + a custom endpoint, so any
S3-compatible store works unchanged.

---

## Enabling real OCR + CLIP embeddings
The default backends (`none` / `hash`) need no heavy ML. For PaddleOCR labels and OpenCLIP
semantic embeddings, build the image with the ML extra and set the matching backends on both
services:
```bash
docker build --build-arg INSTALL_ML=true -t docai-backend:ml backend
# env: APP_OCR_BACKEND=paddle  APP_EMBEDDING_BACKEND=openclip
```
> The embedding backend must be identical on the API (query vectors) and the worker (stored
> vectors), or similarity search is meaningless.

---

## Production checklist
- [ ] `APP_JWT_SECRET` is a strong, unique secret (the config validator rejects the default in prod).
- [ ] `APP_DB_REQUIRE_SSL=true` for Neon/managed Postgres.
- [ ] `APP_CORS_ALLOW_ORIGINS` is the exact frontend origin (not `*`).
- [ ] Migrations applied (`alembic upgrade head`, idempotent).
- [ ] Health check `/health/ready` returns `database: ok`.
- [ ] (If used) ClamAV enabled and reachable; otherwise uploads are not AV-scanned.

## Free-tier behaviour
Free Render/Neon resources sleep when idle — the first request after sleep takes ~30–60s. Because
the job queue is durable in Postgres, any uploads that arrived while the service was waking are
processed as soon as the in-process worker resumes; nothing is lost.
