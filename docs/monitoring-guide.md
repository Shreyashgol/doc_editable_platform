# Monitoring Guide

The platform emits the three pillars: **structured logs**, **metrics**, and **traces**, all
correlated by a request/correlation id.

## Logs
- `structlog` renders JSON to stdout (`APP_LOG_JSON=true`). Ship stdout to your log store.
- Every line carries `correlation_id`. The API sets it from the `X-Correlation-ID` header (or
  generates one) and echoes it back; the worker sets it from the task payload, so one document's
  journey across API + all worker stages shares one id.
- Secrets are redacted by a log processor (`password`, `jwt_secret`, `authorization`, …).

## Metrics (Prometheus)
- Scrape `GET /metrics` on the API (configured in `infra/prometheus/prometheus.yml`).
- Exposed:
  - `http_requests_total{method,path,status}` — throughput & error rate.
  - `http_request_duration_seconds{method,path}` — latency histogram (p50/p95/p99).
- Recommended additional collectors:
  - **Queue depth / DLQ:** export `SELECT status, count(*) FROM pipeline_tasks GROUP BY status`
    via a postgres-exporter query. Alert when `status='dead' > 0` and on growing `pending`.
  - **Per-stage duration:** `processing_jobs.timings` (jsonb) per document; aggregate for
    stage-level SLOs.

## Suggested alerts
| Alert | Condition |
|-------|-----------|
| Pipeline dead-letters | `pipeline_tasks` rows with `status='dead'` > 0 |
| Queue backlog | pending tasks rising / oldest `run_after` age beyond threshold |
| API error budget | `rate(http_requests_total{status=~"5.."}[5m])` over budget |
| Latency SLO | p99 `http_request_duration_seconds` > target |
| Readiness | `/health/ready` failing (DB unreachable) |
| Stuck leases | running tasks with `locked_at` older than the visibility timeout (should self-heal via reclaim; alert if persistent) |

## Tracing (OpenTelemetry)
- Enable with `APP_OTEL_ENABLED=true` and `APP_OTEL_EXPORTER_ENDPOINT`. Instrument FastAPI via
  `opentelemetry-instrumentation-fastapi`; propagate trace context into task payloads so the
  worker continues the same trace across the async boundary.

## Health
- `GET /health/live` — process up (liveness probe).
- `GET /health/ready` — dependencies reachable (DB); returns 503 when degraded (readiness probe).

## Dashboards
Grafana ships in compose (`:3000`). Build panels for: request rate/latency/errors, queue depth
by status, per-stage processing time, and document throughput (COMPLETED/day).
