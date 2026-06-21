# Security Guide

Defense in depth across authn/z, the upload path, transport, and operations.

## Authentication & authorization
- **JWT**: short-lived access tokens + rotating refresh tokens (`infrastructure/security/jwt.py`).
  Token `type` is checked so a refresh token can't be used as an access token.
- **Passwords**: Argon2id (`argon2-cffi`) — memory-hard, OWASP-recommended.
- **RBAC**: `Principal` carries roles; services call `require_role` / `require_owner_or_admin`.
  Every document/symbol/graph operation enforces ownership (admins bypass). Vector search is
  scoped to the caller's documents unless admin.

## Upload security pipeline (fail-closed, ordered)
`size cap → magic bytes (%PDF-) → MIME allow-list → filename sanitization → ClamAV scan →
persist`. Then, in the worker's VALIDATE stage: structural parse + **page-count and per-page
pixel caps** (PDF-bomb / decompression-bomb defense). Any failure rejects (422) or dead-letters
without reaching later stages.
- **ClamAV** via the `VirusScanner` port (`clamav.py`, INSTREAM). Disable only in dev
  (`NullVirusScanner`), never in production.
- **PDF bombs**: `max_pdf_pages`, `max_page_pixels`, render timeout, and (in production) worker
  memory cgroup limits.
- Filenames are sanitized and storage keys are derived server-side (`raw/{owner}/{id}.pdf`),
  preventing path traversal. Artifact bytes are stored via the `ObjectStore` port — either a
  dedicated `object_blobs` table or an S3-compatible bucket — never inline in entity/metadata rows.

## Transport & headers
- TLS terminated at the ingress/LB; DB connections use SSL (`APP_DB_REQUIRE_SSL`).
- Security headers on every response: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, a restrictive `Content-Security-Policy`, and HSTS.

## Rate limiting
- In-process token-bucket (`rate_limit.py`), per-principal/IP, stricter on `auth`/`upload`.
- **Known limitation (ADR 0005):** per-replica, not global. For strict global limits, back the
  limiter with a Postgres counter or an edge/WAF rate limiter.

## Input validation
- Pydantic v2 strict request models on every endpoint; query bounds (`ge/le`) on pagination and
  `top_k`. Errors return RFC-9457 `application/problem+json` with a stable machine `code` and the
  correlation id — never stack traces.

## Secrets management
- All secrets via environment / platform secret manager. `.env` is gitignored; `.env.example`
  documents the keys. `APP_JWT_SECRET` is **validated to be non-default in production**.
- Logs redact secret-like keys. Never bake secrets into images.

## Auditing
- Append-only `audit_logs` records actor, action, before/after, and correlation id for every
  mutating operation (upload, cancel, reprocess, symbol edits, property changes, graph edits,
  pipeline completion/failure). Queryable by admins at `GET /api/v1/audit`.

## Supply chain & CI
- CI runs `bandit` (SAST), `pip-audit` (dependency CVEs), and `trivy` (image scan). Pin and
  review dependencies; flip trivy/pip-audit to blocking once the baseline is clean.

## Least privilege (production)
- Distinct DB role per service with minimal grants; scoped object-store credentials; network
  policies isolating DB/object-store from the public tier; run containers as non-root (Dockerfile
  uses `appuser`).

## Threats explicitly mitigated (see also docs/01 risk register)
PDF bombs (R1), malicious PDFs/embedded payloads (R2, no JS execution, isolated worker),
poison messages (R5, bounded retries → DLQ), secret leakage (R9), and unauthorized cross-tenant
access (ownership checks + owner-scoped search).
