"""Twelve-Factor configuration: all settings from the environment, parsed once.

The same image runs in every environment; only environment variables differ. Nothing here
branches on an environment name — behaviour differences come from values, not code paths.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="APP_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # --- App ---
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    project_name: str = "Document AI Platform"

    # --- Security ---
    jwt_secret: str = Field(default="change-me-in-prod", min_length=8)
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 900  # 15 min
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 14  # 14 days
    rate_limit_per_minute: int = 120
    upload_rate_limit_per_minute: int = 10

    # --- Upload / validation guards (PDF-bomb defenses) ---
    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MB
    max_pdf_pages: int = 500
    max_page_pixels: int = 40_000_000  # ~ guards decompression bombs per page
    render_dpi: int = 200
    render_timeout_seconds: int = 60
    allowed_mime_types: tuple[str, ...] = ("application/pdf",)

    # --- Database ---
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://docai:docai@localhost:5432/docai"  # type: ignore[arg-type]
    )
    database_sync_url: PostgresDsn = Field(
        default="postgresql+psycopg://docai:docai@localhost:5432/docai"  # type: ignore[arg-type]
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    # Neon (and most managed PG) require TLS. Neon's pooled endpoint runs PgBouncer in
    # transaction mode, which is incompatible with asyncpg prepared-statement caching, so we
    # disable it when SSL/pooling is in play. Set APP_DB_REQUIRE_SSL=true for Neon.
    db_require_ssl: bool = False

    # --- Redis / Celery ---
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")  # type: ignore[arg-type]
    celery_broker_url: RedisDsn = Field(default="redis://localhost:6379/1")  # type: ignore[arg-type]
    celery_result_backend: RedisDsn = Field(default="redis://localhost:6379/2")  # type: ignore[arg-type]
    task_max_retries: int = 5
    task_retry_backoff_base_seconds: int = 2
    task_soft_time_limit_seconds: int = 240
    task_hard_time_limit_seconds: int = 300

    # --- Object storage (MinIO / S3) ---
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "documents"
    s3_use_ssl: bool = False
    presign_ttl_seconds: int = 3600

    # --- AV scanning ---
    clamav_host: str = "localhost"
    clamav_port: int = 3310
    clamav_enabled: bool = True

    # --- ML / embeddings ---
    embedding_model: str = "ViT-B-32"
    embedding_pretrained: str = "laion2b_s34b_b79k"
    embedding_dim: int = 512
    classifier_strategy: Literal["rule", "ml", "vit"] = "rule"

    # --- Observability ---
    log_level: str = "INFO"
    log_json: bool = True
    otel_enabled: bool = False
    otel_exporter_endpoint: str | None = None
    service_name: str = "docai-api"

    @field_validator("jwt_secret")
    @classmethod
    def _no_default_secret_in_prod(cls, v: str, info) -> str:  # type: ignore[no-untyped-def]
        if info.data.get("environment") == "production" and v == "change-me-in-prod":
            raise ValueError("APP_JWT_SECRET must be set in production")
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached singleton. Tests override by clearing the cache or injecting a Settings instance."""
    return Settings()
