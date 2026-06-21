"""pipeline_tasks durable job queue (ADR 0005)

Revision ID: 0002_pipeline_tasks
Revises: 0001_baseline
Create Date: 2026-06-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002_pipeline_tasks"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_tasks",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="5"),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(64), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "stage", name="uq_task_doc_stage"),
    )
    op.create_index("ix_tasks_claim", "pipeline_tasks", ["status", "run_after"])
    op.create_index("ix_tasks_locked", "pipeline_tasks", ["locked_at"])
    op.execute(
        "CREATE TRIGGER trg_pipeline_tasks_updated_at BEFORE UPDATE ON pipeline_tasks "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_pipeline_tasks_updated_at ON pipeline_tasks")
    op.drop_index("ix_tasks_locked", table_name="pipeline_tasks")
    op.drop_index("ix_tasks_claim", table_name="pipeline_tasks")
    op.drop_table("pipeline_tasks")
