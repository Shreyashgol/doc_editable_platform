"""Integration test fixtures — run against the configured Postgres (Neon) with pgvector.

Each test runs inside a transaction that is rolled back, so the database is never mutated
permanently and tests are isolated and order-independent. Skips cleanly if no DB is configured.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.db.base import create_engine_and_sessionmaker

_HAS_DB = bool(os.getenv("APP_DATABASE_URL"))

pytestmark = pytest.mark.skipif(not _HAS_DB, reason="APP_DATABASE_URL not configured")


@pytest_asyncio.fixture
async def engine():
    # Function-scoped so the engine is created on the same event loop pytest-asyncio uses for
    # each test (asyncpg connections are bound to the loop that created them).
    eng, _ = create_engine_and_sessionmaker(get_settings())
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    """A session bound to a transaction that is always rolled back after the test."""
    connection = await engine.connect()
    transaction = await connection.begin()
    sess = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        yield sess
    finally:
        await sess.close()
        await transaction.rollback()
        await connection.close()
