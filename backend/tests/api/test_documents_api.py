"""End-to-end API tests: auth, upload validation pipeline, status, dedupe, cancel, RBAC."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text

pytestmark = pytest.mark.api

MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


async def test_health_endpoints(client: AsyncClient):
    assert (await client.get("/health/live")).status_code == 200
    ready = await client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"]["database"] == "ok"


async def test_unauthenticated_request_is_problem_json(client: AsyncClient):
    resp = await client.get("/api/v1/documents")
    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["code"] == "unauthenticated"
    assert "correlation_id" in body


async def test_register_login_and_list_empty(client: AsyncClient, auth):
    headers, _ = auth
    resp = await client.get("/api/v1/documents", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


async def test_upload_happy_path_enqueues_validate(client: AsyncClient, auth, container):
    headers, _ = auth
    resp = await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("drawing.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "UPLOADED"
    assert body["deduplicated"] is False
    doc_id = body["id"]

    # status endpoint
    status_resp = await client.get(f"/api/v1/documents/{doc_id}/status", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "UPLOADED"

    # transactional outbox: a validate task was enqueued in the same commit
    async with container.session_factory() as s:
        row = (
            await s.execute(
                text("SELECT stage, status FROM pipeline_tasks WHERE document_id = :d"),
                {"d": doc_id},
            )
        ).first()
    assert row is not None and row.stage == "validate" and row.status == "pending"


async def test_upload_rejects_non_pdf(client: AsyncClient, auth):
    headers, _ = auth
    resp = await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("evil.pdf", b"not a pdf at all", "application/pdf")},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "file_validation_error"


async def test_upload_empty_file_rejected(client: AsyncClient, auth):
    headers, _ = auth
    resp = await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert resp.status_code == 422


async def test_upload_is_idempotent_by_content_hash(client: AsyncClient, auth):
    headers, _ = auth
    files = {"file": ("a.pdf", MINIMAL_PDF, "application/pdf")}
    first = await client.post("/api/v1/documents", headers=headers, files=files)
    second = await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("b.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["deduplicated"] is True


async def test_cancel_document(client: AsyncClient, auth):
    headers, _ = auth
    up = await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("c.pdf", MINIMAL_PDF, "application/pdf")},
    )
    doc_id = up.json()["id"]
    cancel = await client.post(f"/api/v1/documents/{doc_id}/cancel", headers=headers)
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "CANCELLED"


async def test_cannot_access_another_users_document(client: AsyncClient, auth, created_owners):
    headers_a, _ = auth
    up = await client.post(
        "/api/v1/documents",
        headers=headers_a,
        files={"file": ("d.pdf", MINIMAL_PDF, "application/pdf")},
    )
    doc_id = up.json()["id"]

    # second user
    import uuid
    from uuid import UUID

    email = f"apitest-{uuid.uuid4().hex}@example.com"
    reg = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "supersecret1"}
    )
    created_owners.append(UUID(reg.json()["id"]))
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "supersecret1"}
    )
    headers_b = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get(f"/api/v1/documents/{doc_id}", headers=headers_b)
    assert resp.status_code == 403
    assert resp.json()["code"] == "forbidden"
