"""object_blobs table for the Postgres-backed object store

Revision ID: 0003_object_blobs
Revises: 0002_pipeline_tasks
Create Date: 2026-06-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_object_blobs"
down_revision = "0002_pipeline_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "object_blobs",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("content_type", sa.Text, nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("object_blobs")
