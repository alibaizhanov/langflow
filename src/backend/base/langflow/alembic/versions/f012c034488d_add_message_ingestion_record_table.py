"""add_message_ingestion_record_table

Replace the 1:1 ingestion_job_id / ingestion_timestamp columns on the message
table with a proper M-N join table (message_ingestion_record).

One record per (message_id, session_id, memory_base_id) tracks which messages
were ingested into which Memory Base by which job. Records are written only after
a confirmed successful Chroma write.

Data migration: existing ingestion_job_id values are discarded — they encode
broken 1:1 semantics and cannot be reconstructed without memory_base_id context.
MemoryBaseSession.cursor_id positions remain valid.

Phase: CONTRACT (drop columns) + EXPAND (create table)

Revision ID: f012c034488d
Revises: 7dfcd1cfd6c9
Create Date: 2026-04-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from langflow.utils import migration

revision: str = "f012c034488d"
down_revision: str | None = "7dfcd1cfd6c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create the M-N join table
    if not migration.table_exists("message_ingestion_record", conn):
        op.create_table(
            "message_ingestion_record",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column(
                "message_id",
                sa.Uuid(),
                sa.ForeignKey("message.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "memory_base_id",
                sa.Uuid(),
                sa.ForeignKey("memory_base.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "job_id",
                sa.Uuid(),
                sa.ForeignKey("job.job_id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "message_id", "session_id", "memory_base_id",
                name="uq_mir_message_session_mb",
            ),
        )
        op.create_index("ix_mir_message_id", "message_ingestion_record", ["message_id"])
        op.create_index("ix_mir_job_id", "message_ingestion_record", ["job_id"])
        op.create_index(
            "ix_mir_memory_base_session",
            "message_ingestion_record",
            ["memory_base_id", "session_id"],
        )

    # 2. Data migration verification: SELECT COUNT of rows whose ingestion_job_id
    #    will be discarded, for audit purposes.  The 1:1 values cannot be promoted
    #    to message_ingestion_record rows because memory_base_id is not stored on
    #    the message table; see module docstring for rationale.
    if migration.column_exists("message", "ingestion_job_id", conn):
        _count_result = conn.execute(
            sa.text("SELECT COUNT(*) FROM message WHERE ingestion_job_id IS NOT NULL")
        )
        _discarded = _count_result.scalar() or 0
        if _discarded:
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "f012c034488d: discarding %d ingestion_job_id value(s) from message table "
                "(non-migratable — no memory_base_id context available).",
                _discarded,
            )

    # 3. Drop the superseded 1:1 columns from message.
    with op.batch_alter_table("message", schema=None) as batch_op:
        if migration.column_exists("message", "ingestion_job_id", conn):
            batch_op.drop_column("ingestion_job_id")
        if migration.column_exists("message", "ingestion_timestamp", conn):
            batch_op.drop_column("ingestion_timestamp")


def downgrade() -> None:
    conn = op.get_bind()

    # CONTRACT phase: downgrade re-adds the 1:1 columns but all data in
    # message_ingestion_record is permanently discarded.  Raise a hard error in
    # production environments to prevent accidental data loss; remove this guard
    # only in controlled development rollback scenarios.
    raise NotImplementedError(
        "f012c034488d downgrade: message_ingestion_record data will be permanently lost. "
        "Remove this guard only if you have verified there is no data to preserve."
    )

    # Re-add 1:1 columns to message (data is lost on downgrade — expected)
    with op.batch_alter_table("message", schema=None) as batch_op:  # type: ignore[unreachable]
        if not migration.column_exists("message", "ingestion_timestamp", conn):
            batch_op.add_column(sa.Column("ingestion_timestamp", sa.DateTime(), nullable=True))
        if not migration.column_exists("message", "ingestion_job_id", conn):
            batch_op.add_column(sa.Column("ingestion_job_id", sa.Uuid(), nullable=True))

    # Drop join table
    if migration.table_exists("message_ingestion_record", conn):
        op.drop_index("ix_mir_memory_base_session", table_name="message_ingestion_record")
        op.drop_index("ix_mir_job_id", table_name="message_ingestion_record")
        op.drop_index("ix_mir_message_id", table_name="message_ingestion_record")
        op.drop_table("message_ingestion_record")
