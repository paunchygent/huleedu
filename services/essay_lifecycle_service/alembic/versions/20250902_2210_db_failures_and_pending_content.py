"""Add DB tables for validation failures and pending content; extend slot status

Revision ID: 4a7c2c11b9e0
Revises: 2f9b1a77a1c3
Create Date: 2025-09-02 22:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4a7c2c11b9e0"
down_revision: str | Sequence[str] | None = "2f9b1a77a1c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Extend slot status to include 'failed'
    op.drop_constraint("ck_slot_status_valid", "slot_assignments", type_="check")
    op.create_check_constraint(
        "ck_slot_status_valid",
        "slot_assignments",
        "status IN ('available','assigned','failed')",
    )

    # Create batch_validation_failures table
    op.create_table(
        "batch_validation_failures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.String(length=255), nullable=False),
        sa.Column("batch_tracker_id", sa.Integer(), nullable=True),
        sa.Column("file_upload_id", sa.String(length=255), nullable=True),
        sa.Column("validation_error_code", sa.String(length=50), nullable=True),
        sa.Column("validation_error_detail", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(
            ["batch_tracker_id"], ["batch_essay_trackers.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("idx_failures_batch", "batch_validation_failures", ["batch_tracker_id"])
    op.create_index("idx_failures_batch_id", "batch_validation_failures", ["batch_id"])

    # Create batch_pending_content table
    op.create_table(
        "batch_pending_content",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.String(length=255), nullable=False),
        sa.Column("text_storage_id", sa.String(length=255), nullable=False),
        sa.Column("content_metadata", sa.dialects.postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("batch_id", "text_storage_id", name="uq_pending_content_per_batch"),
    )
    op.create_index("idx_pending_content_batch", "batch_pending_content", ["batch_id"])

    # Create additional indexes per guidance names
    op.create_index(
        "idx_slot_batch_status",
        "slot_assignments",
        ["batch_tracker_id", "status"],
    )
    op.create_index(
        "idx_slot_idempotency",
        "slot_assignments",
        ["batch_tracker_id", "text_storage_id"],
        unique=False,
        postgresql_where=sa.text("text_storage_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_slot_idempotency", table_name="slot_assignments")
    op.drop_index("idx_slot_batch_status", table_name="slot_assignments")
    op.drop_index("idx_pending_content_batch", table_name="batch_pending_content")
    op.drop_table("batch_pending_content")
    op.drop_index("idx_failures_batch_id", table_name="batch_validation_failures")
    op.drop_index("idx_failures_batch", table_name="batch_validation_failures")
    op.drop_table("batch_validation_failures")

    # Revert slot status check to previous two-state constraint
    op.drop_constraint("ck_slot_status_valid", "slot_assignments", type_="check")
    op.create_check_constraint(
        "ck_slot_status_valid",
        "slot_assignments",
        "status IN ('available','assigned')",
    )
