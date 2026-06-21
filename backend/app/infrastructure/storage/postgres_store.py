"""Postgres-backed object store.

Stores artifact bytes in an ``object_blobs`` table so a deployment needs only the database —
no MinIO/S3/GCS to provision. It implements the same ``ObjectStore`` port as ``S3ObjectStore``,
so it is a pure configuration swap (``APP_OBJECT_STORE_BACKEND=postgres``).

It uses a synchronous SQLAlchemy engine (the port is sync, boto3-style; async callers already
wrap object-store calls in ``asyncio.to_thread``). Trade-off: blobs in the relational store
don't scale like object storage — intended for demos/single-datastore deploys, not millions of
documents. Flip back to ``s3`` to use object storage.
"""

from __future__ import annotations

from sqlalchemy import create_engine, text

from ...core.config import Settings
from ...core.errors import InfrastructureError
from ...domain.ports import ObjectStore


class PostgresObjectStore(ObjectStore):
    def __init__(self, settings: Settings) -> None:
        connect_args = {"sslmode": "require"} if settings.db_require_ssl else {}
        # NullPool-ish small pool; object ops are short-lived.
        self._engine = create_engine(
            str(settings.database_sync_url),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            connect_args=connect_args,
        )

    def put(self, key: str, data: bytes, content_type: str) -> str:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO object_blobs (key, content_type, data)
                        VALUES (:k, :ct, :d)
                        ON CONFLICT (key) DO UPDATE
                            SET content_type = EXCLUDED.content_type, data = EXCLUDED.data
                        """
                    ),
                    {"k": key, "ct": content_type, "d": data},
                )
        except Exception as exc:  # pragma: no cover - infra
            raise InfrastructureError(f"object store put failed: {exc}") from exc
        return key

    def get(self, key: str) -> bytes:
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    text("SELECT data FROM object_blobs WHERE key = :k"), {"k": key}
                ).first()
        except Exception as exc:  # pragma: no cover - infra
            raise InfrastructureError(f"object store get failed: {exc}") from exc
        if row is None:
            raise InfrastructureError(f"object not found: {key}")
        return bytes(row[0])

    def presign_get(self, key: str, ttl_seconds: int) -> str:
        # No external URL for DB blobs; artifacts are served via the authenticated API if needed.
        return f"db://{key}"

    def delete_prefix(self, prefix: str) -> None:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM object_blobs WHERE key LIKE :p"), {"p": f"{prefix}%"}
                )
        except Exception as exc:  # pragma: no cover - infra
            raise InfrastructureError(f"object store delete failed: {exc}") from exc
