"""Audit endpoint: admin-only RBAC and querying."""

from __future__ import annotations

import uuid

import pytest
from app.domain.entities import User
from app.domain.enums import Role
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.security.passwords import hash_password
from httpx import AsyncClient

pytestmark = pytest.mark.api

MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


async def test_audit_requires_admin(client: AsyncClient, auth):
    headers, _ = auth  # engineer role
    resp = await client.get("/api/v1/audit", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "forbidden"


async def test_admin_can_query_audit(client: AsyncClient, container, created_owners):
    # Seed an admin directly, then authenticate.
    email = f"admin-{uuid.uuid4().hex}@example.com"
    uow = SqlAlchemyUnitOfWork(container.session_factory, container.settings)
    admin = User(email=email, password_hash=hash_password("supersecret1"), roles={Role.ADMIN})
    async with uow:
        await uow.users.add(admin)
        await uow.commit()
    created_owners.append(admin.id)

    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "supersecret1"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # An upload writes an audit entry (actor = admin).
    await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("a.pdf", MINIMAL_PDF, "application/pdf")},
    )

    resp = await client.get("/api/v1/audit?entity_type=document", headers=headers)
    assert resp.status_code == 200
    actions = {e["action"] for e in resp.json()}
    assert "upload" in actions
