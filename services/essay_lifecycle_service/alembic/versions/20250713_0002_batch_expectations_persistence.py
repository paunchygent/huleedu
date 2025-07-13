"""Add batch expectations persistence support

Revision ID: 20250713_0002
Revises: 20250706_0001
Create Date: 2025-07-13 23:30:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20250713_0002"
down_revision = "20250706_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add batch expectations persistence to support service restart robustness."""

    # Add new columns to batch_essay_trackers table for batch expectations persistence
    op.add_column("batch_essay_trackers", sa.Column("expected_essay_ids", sa.JSON(), nullable=True))
    op.add_column("batch_essay_trackers", sa.Column("available_slots", sa.JSON(), nullable=True))
    op.add_column("batch_essay_trackers", sa.Column("expected_count", sa.Integer(), nullable=True))
    op.add_column(
        "batch_essay_trackers", sa.Column("course_code", sa.String(length=50), nullable=True)
    )
    op.add_column("batch_essay_trackers", sa.Column("essay_instructions", sa.Text(), nullable=True))
    op.add_column(
        "batch_essay_trackers", sa.Column("user_id", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "batch_essay_trackers", sa.Column("correlation_id", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "batch_essay_trackers",
        sa.Column("timeout_seconds", sa.Integer(), nullable=True, server_default=sa.text("300")),
    )

    # Make batch_id unique to prevent duplicate registrations
    op.create_unique_constraint(
        "uq_batch_essay_trackers_batch_id", "batch_essay_trackers", ["batch_id"]
    )

    # Create slot_assignments table for normalized slot tracking
    op.create_table(
        "slot_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_tracker_id", sa.Integer(), nullable=False),
        sa.Column("internal_essay_id", sa.String(length=255), nullable=False),
        sa.Column("text_storage_id", sa.String(length=255), nullable=False),
        sa.Column("original_file_name", sa.String(length=500), nullable=False),
        sa.Column("assigned_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_tracker_id"], ["batch_essay_trackers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_slot_assignments_batch_tracker_id"),
        "slot_assignments",
        ["batch_tracker_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_slot_assignments_internal_essay_id"),
        "slot_assignments",
        ["internal_essay_id"],
        unique=False,
    )

    # Update existing records to have default values for new columns (if any exist)
    op.execute("""
        UPDATE batch_essay_trackers 
        SET expected_essay_ids = '[]'::json,
            available_slots = '[]'::json,
            expected_count = total_slots,
            timeout_seconds = 300
        WHERE expected_essay_ids IS NULL
    """)

    # Now make the new columns NOT NULL (after setting defaults)
    op.alter_column("batch_essay_trackers", "expected_essay_ids", nullable=False)
    op.alter_column("batch_essay_trackers", "available_slots", nullable=False)
    op.alter_column("batch_essay_trackers", "expected_count", nullable=False)
    op.alter_column("batch_essay_trackers", "timeout_seconds", nullable=False)


def downgrade() -> None:
    """Remove batch expectations persistence support."""

    # Drop slot_assignments table
    op.drop_index(op.f("ix_slot_assignments_internal_essay_id"), table_name="slot_assignments")
    op.drop_index(op.f("ix_slot_assignments_batch_tracker_id"), table_name="slot_assignments")
    op.drop_table("slot_assignments")

    # Drop unique constraint on batch_id
    op.drop_constraint("uq_batch_essay_trackers_batch_id", "batch_essay_trackers", type_="unique")

    # Remove new columns from batch_essay_trackers
    op.drop_column("batch_essay_trackers", "timeout_seconds")
    op.drop_column("batch_essay_trackers", "correlation_id")
    op.drop_column("batch_essay_trackers", "user_id")
    op.drop_column("batch_essay_trackers", "essay_instructions")
    op.drop_column("batch_essay_trackers", "course_code")
    op.drop_column("batch_essay_trackers", "expected_count")
    op.drop_column("batch_essay_trackers", "available_slots")
    op.drop_column("batch_essay_trackers", "expected_essay_ids")
