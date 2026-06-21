"""Observability & security middleware: metrics, secure headers, correlation id, rate limiting."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.api


async def test_metrics_endpoint_exposes_prometheus(client: AsyncClient):
    await client.get("/health/live")  # generate at least one metric sample
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "http_requests_total" in resp.text


async def test_secure_headers_and_correlation_id(client: AsyncClient):
    resp = await client.get("/health/live")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert "X-Correlation-ID" in resp.headers


async def test_incoming_correlation_id_is_echoed(client: AsyncClient):
    resp = await client.get("/health/live", headers={"X-Correlation-ID": "trace-abc"})
    assert resp.headers["X-Correlation-ID"] == "trace-abc"


async def test_rate_limit_triggers_on_strict_path(client: AsyncClient):
    # /auth/* uses the strict bucket (default capacity 10). Hammer past it.
    statuses = []
    for _ in range(15):
        r = await client.post(
            "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"}
        )
        statuses.append(r.status_code)
    assert 429 in statuses
    limited = next(r for r in statuses if r == 429)
    assert limited == 429
