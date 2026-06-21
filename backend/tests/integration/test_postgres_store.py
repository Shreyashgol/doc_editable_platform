"""Integration test for the Postgres-backed object store (runs against the configured DB)."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from app.core.config import Settings
from app.core.errors import InfrastructureError
from app.infrastructure.storage.postgres_store import PostgresObjectStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("APP_DATABASE_URL"), reason="APP_DATABASE_URL not configured"),
]


def test_postgres_object_store_roundtrip():
    store = PostgresObjectStore(Settings(object_store_backend="postgres"))
    prefix = f"test/{uuid4().hex}/"
    key = f"{prefix}crop.png"
    data = b"\x89PNG\r\n binary blob"

    store.put(key, data, "image/png")
    assert store.get(key) == data

    # upsert overwrites
    store.put(key, b"updated", "image/png")
    assert store.get(key) == b"updated"

    assert store.presign_get(key, 60).startswith("db://")

    store.delete_prefix(prefix)
    with pytest.raises(InfrastructureError):
        store.get(key)


def test_postgres_object_store_missing_key():
    store = PostgresObjectStore(Settings(object_store_backend="postgres"))
    with pytest.raises(InfrastructureError):
        store.get(f"nope/{uuid4().hex}.bin")
