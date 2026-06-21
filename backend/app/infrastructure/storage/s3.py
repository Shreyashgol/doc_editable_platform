"""Object storage adapters (S3/MinIO + an in-memory fake for tests).

Symbols reference artifacts by key; bytes never enter Postgres. Synchronous (boto3); async
callers wrap calls in ``asyncio.to_thread``.
"""

from __future__ import annotations

import threading

from ...core.config import Settings
from ...core.errors import InfrastructureError
from ...domain.ports import ObjectStore


class S3ObjectStore(ObjectStore):
    def __init__(self, settings: Settings) -> None:
        import boto3
        from botocore.config import Config

        self._bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            use_ssl=settings.s3_use_ssl,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )
        self._presign_ttl = settings.presign_ttl_seconds

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:
            self._client.create_bucket(Bucket=self._bucket)

    def put(self, key: str, data: bytes, content_type: str) -> str:
        try:
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        except Exception as exc:  # pragma: no cover - network
            raise InfrastructureError(f"object store put failed: {exc}") from exc
        return key

    def get(self, key: str) -> bytes:
        try:
            return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except Exception as exc:  # pragma: no cover - network
            raise InfrastructureError(f"object store get failed: {exc}") from exc

    def presign_get(self, key: str, ttl_seconds: int) -> str:
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=ttl_seconds
        )

    def delete_prefix(self, prefix: str) -> None:
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objs:
                self._client.delete_objects(Bucket=self._bucket, Delete={"Objects": objs})


class InMemoryObjectStore(ObjectStore):
    """Thread-safe in-memory store for tests and local runs without MinIO."""

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}
        self._lock = threading.Lock()

    def put(self, key: str, data: bytes, content_type: str) -> str:
        with self._lock:
            self._data[key] = data
        return key

    def get(self, key: str) -> bytes:
        with self._lock:
            if key not in self._data:
                raise InfrastructureError(f"object not found: {key}")
            return self._data[key]

    def presign_get(self, key: str, ttl_seconds: int) -> str:
        return f"memory://{key}?ttl={ttl_seconds}"

    def delete_prefix(self, prefix: str) -> None:
        with self._lock:
            for k in [k for k in self._data if k.startswith(prefix)]:
                del self._data[k]
