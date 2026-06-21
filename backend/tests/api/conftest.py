"""API test harness — the real FastAPI app against the configured Neon DB, with the object
store and virus scanner replaced by in-memory fakes. Test-created rows are cleaned up after.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.container import Container
from app.infrastructure.security.clamav import NullVirusScanner
from app.infrastructure.storage.s3 import InMemoryObjectStore
from app.interfaces.http.app import create_app

_HAS_DB = bool(os.getenv("APP_DATABASE_URL"))
pytestmark = pytest.mark.skipif(not _HAS_DB, reason="APP_DATABASE_URL not configured")

MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest_asyncio.fixture
async def container() -> AsyncIterator[Container]:
    settings = get_settings()
    c = Container(
        settings,
        object_store=InMemoryObjectStore(),
        virus_scanner=NullVirusScanner(),
    )
    yield c
    await c.dispose()


@pytest_asyncio.fixture
async def created_owners() -> list[UUID]:
    return []


@pytest_asyncio.fixture
async def client(container: Container, created_owners: list[UUID]) -> AsyncIterator[AsyncClient]:
    app = create_app(settings=container.settings, container=container)
    app.state.container = container  # ASGITransport does not run lifespan events
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    # Cleanup: remove any rows created by this test (documents cascade to tasks).
    if created_owners:
        async with container.session_factory() as s:
            await s.execute(
                text("DELETE FROM documents WHERE owner_id = ANY(:ids)"),
                {"ids": [str(o) for o in created_owners]},
            )
            await s.execute(
                text("DELETE FROM audit_logs WHERE actor_id = ANY(:ids)"),
                {"ids": [str(o) for o in created_owners]},
            )
            await s.execute(
                text("DELETE FROM users WHERE id = ANY(:ids)"),
                {"ids": [str(o) for o in created_owners]},
            )
            await s.commit()


@pytest_asyncio.fixture
async def auth(client: AsyncClient, created_owners: list[UUID]):
    """Register a unique user, log in, and return (headers, user_id)."""
    import uuid

    email = f"apitest-{uuid.uuid4().hex}@example.com"
    reg = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "supersecret1"}
    )
    assert reg.status_code == 201, reg.text
    user_id = UUID(reg.json()["id"])
    created_owners.append(user_id)
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "supersecret1"}
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, user_id
