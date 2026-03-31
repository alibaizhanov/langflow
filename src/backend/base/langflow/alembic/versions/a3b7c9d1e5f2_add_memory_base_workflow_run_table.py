"""add_memory_base_workflow_run_table

Introduce a per-session, per-memory-base tracking table for WORKFLOW job runs.

Each row represents one WORKFLOW job run scoped to a (memory_base_id, session_id) pair.
The ``ingestion_job_id`` column is NULL while the run is "pending" (not yet covered by a
completed ingestion cycle) and is stamped with the ingestion job UUID once ingestion
completes successfully.

Count pending for threshold evaluation:
    SELECT COUNT(*) FROM memory_base_workflow_run
    WHERE memory_base_id = ? AND session_id = ? AND ingestion_job_id IS NULL

Phase: EXPAND (new table only)

Revision ID: a3b7c9d1e5f2
Revises: f012c034488d
Create Date: 2026-04-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from langflow.utils import migration

revision: str = "a3b7c9d1e5f2"
down_revision: str | None = "f012c034488d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    if not migration.table_exists("memory_base_workflow_run", conn):
        op.create_table(
            "memory_base_workflow_run",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column(
                "memory_base_id",
                sa.Uuid(),
                sa.ForeignKey("memory_base.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column(
                "workflow_job_id",
                sa.Uuid(),
                sa.ForeignKey("job.job_id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "ingestion_job_id",
                sa.Uuid(),
                sa.ForeignKey("job.job_id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "memory_base_id",
                "session_id",
                "workflow_job_id",
                name="uq_mbwr_mb_session_wf_job",
            ),
        )
        op.create_index("ix_mbwr_mb_session", "memory_base_workflow_run", ["memory_base_id", "session_id"])
        op.create_index("ix_mbwr_ingestion_job_id", "memory_base_workflow_run", ["ingestion_job_id"])


def downgrade() -> None:
    conn = op.get_bind()

    if migration.table_exists("memory_base_workflow_run", conn):
        op.drop_index("ix_mbwr_ingestion_job_id", table_name="memory_base_workflow_run")
        op.drop_index("ix_mbwr_mb_session", table_name="memory_base_workflow_run")
        op.drop_table("memory_base_workflow_run")
