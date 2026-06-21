"""baseline schema: pgvector, all tables, HNSW index, updated_at triggers

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-20
"""
from __future__ import annotations

from alembic import op

from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401  (populate metadata)

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

# Trigger keeps updated_at correct even for raw SQL updates that bypass the ORM.
_UPDATED_AT_FN = """
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_TIMESTAMPED_TABLES = [
    "users", "documents", "pages", "processing_jobs", "symbols",
    "symbol_properties", "symbol_versions", "embeddings", "relationships", "audit_logs",
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

    # Approximate-NN index for similarity search (cosine).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_embeddings_hnsw "
        "ON embeddings USING hnsw (embedding vector_cosine_ops)"
    )

    op.execute(_UPDATED_AT_FN)
    for table in _TIMESTAMPED_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )


def downgrade() -> None:
    for table in _TIMESTAMPED_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table}")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
