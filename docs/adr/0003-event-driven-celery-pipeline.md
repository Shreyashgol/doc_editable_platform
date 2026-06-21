# ADR 0003 — Event-driven async pipeline on Celery/Redis with per-stage retryability

- **Status:** Accepted
- **Date:** 2026-06-20

## Context
Symbol extraction is CPU/memory heavy (PDF render, OpenCV, OCR, CLIP). It must not block the API,
must scale independently, survive worker crashes, and let any stage retry without redoing others.

## Decision
Process asynchronously. The API persists the upload and emits `DocumentUploaded`; an
infrastructure adapter maps domain events to a **Celery chain** with a **separate queue per
worker type** (pdf, ocr, classify, embed, graph). A shared base task provides idempotency
(keyed by `document_id`+stage), bounded retries with exponential backoff + jitter, a dead-letter
queue, and OpenTelemetry context propagation. State transitions + audit are written via a
transactional outbox so events are never lost after a commit.

## Consequences
- (+) API returns in <300 ms; throughput bound by worker fleet, autoscaled on queue depth.
- (+) Each stage independently retryable; poison messages land in DLQ + `FAILED` state + alert.
- (+) Domain emits events, never imports Celery → future move to Kafka/NATS is an adapter change.
- (−) Eventual consistency: clients poll/stream status. Accepted; status API + audit make the
  pipeline observable and resumable.

## Alternatives
- **Inline/synchronous processing:** simple but fails reliability, scalability, and latency goals.
- **Custom Redis Streams bus:** more control, but reimplements retries/routing/scheduling that
  Celery provides. Rejected for v1.
