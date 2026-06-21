# Phase 2 — Data, API, Domain & Events

> Database Design · API Design · Domain Modeling · Event Flow Design

---

## 1. Domain Model (DDD)

### 1.1 Aggregates & entities

```
Document (Aggregate Root)
 ├─ identity: id (UUID)
 ├─ owner_id, filename, content_hash, storage_uri, page_count, size_bytes, mime
 ├─ status: ProcessingStatus (state machine)
 ├─ Pages: Page[]            (page_number, width, height, render_uri, dpi)
 └─ Job: ProcessingJob       (current stage, attempts, last_error, timings)

Symbol (Aggregate Root — referenced by Document, edited independently)
 ├─ identity: id (UUID)
 ├─ document_id, page_number
 ├─ type: SymbolType (Valve, PressureVessel, HeatExchanger, ...)
 ├─ label: string | null        (associated from OCR)
 ├─ geometry: BBox + centroid + rotation
 ├─ crop_uri: string            (object-storage reference, NEVER bytes in DB)
 ├─ classification: {method, confidence, raw_class}
 ├─ Properties: SymbolProperty[]  (typed custom key/values)
 ├─ Versions: SymbolVersion[]     (immutable geometry/label/property snapshots)
 └─ Embedding: vector(512)        (pgvector, OpenCLIP)

Relationship (Aggregate Root — the graph edge)
 ├─ id, document_id
 ├─ source_symbol_id, target_symbol_id
 ├─ type: RelationshipType (feeds, controls, measures, connects_to, ...)
 └─ confidence, properties(JSONB)

AuditLog (append-only)
 └─ id, actor_id, entity_type, entity_id, action, before, after, correlation_id, ts
```

### 1.2 Value objects (immutable, no identity)

- `BBox { x, y, width, height }` (page pixel space) with helpers: `area`, `centroid`, `iou`.
- `Centroid { x, y }`.
- `Classification { method: rule|ml|vit, raw_class, confidence }`.
- `ProcessingStatus` (enum, see state machine).
- `SymbolType`, `RelationshipType` (enums, open for extension via config).

### 1.3 Ports (interfaces, defined in `domain`, implemented in `infrastructure`)

```python
DocumentRepository      # persistence of Document aggregate
SymbolRepository        # persistence + vector search of Symbol
RelationshipRepository  # graph edges (Postgres now, Neo4j later)
AuditRepository
ObjectStore             # put/get/presign artifacts (MinIO/S3)
EventPublisher          # emit domain events → broker
PdfParser               # render pages, extract text layer
SymbolExtractor         # CV pipeline → candidate symbols
OcrEngine               # image → tokens+boxes+confidence
SymbolClassifier        # crop/label → Classification  (strategy)
Embedder                # crop → vector                (strategy)
VirusScanner            # bytes → clean|infected
```

This is the heart of extensibility: every external capability is an interface. Swapping
PaddleOCR for Tesseract, or OpenCLIP for a fine-tuned model, or Postgres-graph for Neo4j,
is implementing one adapter — **zero** changes to domain or application layers.

---

## 2. Document Processing State Machine

```
            ┌──────────┐
            │ UPLOADED │
            └────┬─────┘
                 ▼
           ┌────────────┐   invalid    ┌────────┐
           │ VALIDATING ├─────────────▶│ FAILED │◀────────────┐
           └────┬───────┘              └───┬────┘             │
                ▼                          │ (retryable)      │
            ┌────────┐                     ▼                  │
            │ QUEUED │              ┌──────────┐              │
            └───┬────┘              │ RETRYING │              │
                ▼                   └────┬─────┘              │
          ┌────────────┐                 │ re-enters stage    │
          │ PROCESSING │◀────────────────┘                    │
          └────┬───────┘   (pdf parse + symbol extract)       │
               ▼                                              │
        ┌─────────────┐                                       │
        │ OCR_RUNNING │                                       │
        └────┬────────┘                                       │
             ▼                                                │
      ┌──────────────┐                                        │
      │ CLASSIFYING  │                                        │
      └────┬─────────┘                                        │
           ▼                                                  │
      ┌────────────┐                                          │
      │ EMBEDDING  │──────────── any stage exhausts retries ──┘
      └────┬───────┘
           ▼
      ┌───────────┐         ┌───────────┐
      │ COMPLETED │         │ CANCELLED │ (user-initiated, any non-terminal state)
      └───────────┘         └───────────┘
```

**Rules**
- Transitions are validated by the domain (`Document.transition_to(next)` raises on illegal moves).
- Every transition writes a `processing_jobs` update + an `audit_logs` row with timestamps.
- Terminal states: `COMPLETED`, `CANCELLED`, and `FAILED` (after retry exhaustion).
- `RETRYING` records attempt count; backoff handled by Celery `retry` with jitter.

---

## 3. Event-Driven Workflow

```
DocumentUploaded
   └─▶ validate.document            → emits DocumentValidated | DocumentRejected
        └─▶ pdf.extract             → emits PagesExtracted, SymbolsDetected
             └─▶ ocr.run            → emits TextExtracted, LabelsAssociated
                  └─▶ classify.run  → emits SymbolsClassified
                       └─▶ embed.run→ emits EmbeddingsGenerated
                            └─▶ graph.build → emits RelationshipsInferred
                                 └─▶ finalize → emits DocumentCompleted
```

- **Transport:** domain events are published via the `EventPublisher` port. The Celery adapter
  maps each event to the next task in a chain. Chaining preserves ordering per document while
  allowing many documents to flow in parallel.
- **Idempotency:** each task is keyed by `(document_id, stage)`. Re-delivery checks the job's
  `stage_status`; already-completed stages short-circuit. Safe to retry/replay.
- **Retryability:** each stage has its own `max_retries`, backoff, and DLQ. A failure in `embed`
  never re-runs `ocr`.
- **Outbox:** state change + event emission happen in one DB transaction (transactional outbox)
  so we never "commit work but lose the event" (mitigates R8).

---

## 4. Database Design (PostgreSQL + pgvector)

Conventions on **every** table: `id UUID PK DEFAULT gen_random_uuid()`, `created_at timestamptz`,
`updated_at timestamptz` (trigger-maintained), soft constraints via FKs + `ON DELETE` rules.

### 4.1 `documents`
| column | type | notes |
|--------|------|-------|
| id | uuid pk | |
| owner_id | uuid | FK users(id) |
| filename | text | original name (sanitized) |
| content_hash | char(64) | sha256, **unique per owner** for dedupe |
| storage_uri | text | object-storage key of raw PDF |
| mime_type | text | validated `application/pdf` |
| size_bytes | bigint | |
| page_count | int | |
| status | text | enum-checked ProcessingStatus |
| created_at / updated_at | timestamptz | |

Indexes: `(owner_id, status)`, unique `(owner_id, content_hash)`.

### 4.2 `pages`
`id, document_id FK, page_number, width_px, height_px, dpi, render_uri, created_at`.
Unique `(document_id, page_number)`.

### 4.3 `processing_jobs`
`id, document_id FK unique, stage text, stage_status text, attempts int, max_attempts int,
last_error text, started_at, finished_at, timings jsonb, created_at, updated_at`.

### 4.4 `symbols`
| column | type | notes |
|--------|------|-------|
| id | uuid pk | |
| document_id | uuid FK | |
| page_number | int | |
| type | text | SymbolType, nullable until classified |
| label | text | from OCR association |
| bbox | jsonb | `{x,y,width,height}` (also denormalized cols for indexing) |
| bbox_x, bbox_y, bbox_w, bbox_h | numeric | generated/denormalized for spatial queries |
| centroid_x, centroid_y | numeric | |
| rotation | numeric | degrees |
| crop_uri | text | object-storage key — never image bytes |
| classification_method | text | rule\|ml\|vit |
| classification_confidence | numeric | |
| created_at / updated_at | timestamptz | |

Indexes: `(document_id, page_number)`, `(type)`, GIN on `bbox`.

### 4.5 `symbol_properties`
`id, symbol_id FK, key text, value_type text(string|number|bool|date|json), value jsonb,
created_at, updated_at`. Unique `(symbol_id, key)`.

### 4.6 `symbol_versions` (immutable history)
`id, symbol_id FK, version int, snapshot jsonb (geometry+label+type+properties),
changed_by uuid, change_reason text, created_at`. Unique `(symbol_id, version)`.

### 4.7 `embeddings`
`id, symbol_id FK unique, model text, dim int, embedding vector(512), created_at`.
Index: `USING hnsw (embedding vector_cosine_ops)`.
> Kept in its own table so embedding model/version can evolve without touching `symbols`,
> and so vectors are loaded only when needed.

### 4.8 `relationships` (graph edges)
`id, document_id FK, source_symbol_id FK, target_symbol_id FK, type text, confidence numeric,
properties jsonb, created_at, updated_at`. Indexes on `source`, `target`, `(document_id,type)`.
> Adjacency-list model → recursive CTE traversal now; clean export to Neo4j later (R11).

### 4.9 `audit_logs` (append-only)
`id, actor_id, entity_type, entity_id, action, before jsonb, after jsonb, correlation_id,
created_at`. Index `(entity_type, entity_id)`, `(correlation_id)`.

### 4.10 `users` / `roles` (auth)
`users(id, email unique, password_hash, is_active, created_at, updated_at)`,
`roles(id, name)`, `user_roles(user_id, role_id)`. RBAC enforced in application layer.

---

## 5. API Design (REST, versioned `/api/v1`)

Principles: versioned path, Pydantic request+response models, problem+json errors, cursor
pagination, idempotency key on upload, correlation-id propagation, OpenAPI auto-doc.

| Method & path | Purpose | Auth |
|---------------|---------|------|
| `POST /api/v1/auth/login` | Obtain JWT (access+refresh) | public |
| `POST /api/v1/auth/refresh` | Rotate access token | refresh |
| `POST /api/v1/documents` | Upload PDF (multipart) → 202 + document id | user |
| `GET /api/v1/documents` | List (filter by status, paginate) | user |
| `GET /api/v1/documents/{id}` | Document detail + status | owner/admin |
| `GET /api/v1/documents/{id}/status` | Lightweight status + stage timings | owner |
| `POST /api/v1/documents/{id}/cancel` | Cancel processing | owner |
| `POST /api/v1/documents/{id}/reprocess` | Re-run from a stage | owner |
| `GET /api/v1/documents/{id}/symbols` | Symbols (filter by page/type) | owner |
| `GET /api/v1/symbols/{id}` | Symbol detail | owner |
| `PATCH /api/v1/symbols/{id}` | Edit geometry/type/label → new version | owner |
| `GET /api/v1/symbols/{id}/versions` | Version history | owner |
| `PUT /api/v1/symbols/{id}/properties` | Upsert typed custom properties | owner |
| `GET /api/v1/documents/{id}/graph` | Graph (nodes+edges) | owner |
| `POST /api/v1/relationships` | Create edge | owner |
| `DELETE /api/v1/relationships/{id}` | Remove edge | owner |
| `POST /api/v1/search/similar` | Vector similarity (by symbol id or text or uploaded crop) | user |
| `GET /api/v1/audit` | Audit query (entity, actor, range) | admin |
| `GET /health/live` · `GET /health/ready` | Liveness / readiness | public |
| `GET /metrics` | Prometheus exposition | internal |

### 5.1 Upload contract (F1/F2)
`POST /api/v1/documents` (multipart `file`, optional `Idempotency-Key` header) →
**202 Accepted** `{ "id": "...", "status": "UPLOADED", "status_url": "/api/v1/documents/{id}/status" }`.
Validation failures → **422** problem+json with machine-readable `code`.

### 5.2 Similarity search contract (F13)
`POST /api/v1/search/similar` body one of `{symbol_id}` | `{text}` | `{image_b64}` plus
`{top_k, document_id?, type?}` → ranked `[{symbol_id, score, ...}]`. Text path uses OpenCLIP
text tower → same vector space → cross-modal retrieval (foundation for RAG).

### 5.3 Errors
All errors use RFC-9457 `application/problem+json`:
`{ "type", "title", "status", "detail", "code", "correlation_id", "errors": [...] }`.
Typed exceptions in the domain map to HTTP codes in one middleware (Phase 3).
