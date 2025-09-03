"""Evolve slot_assignments to inventory model and pre-seed slots

Revision ID: 2f9b1a77a1c3
Revises: d5a059a89aed
Create Date: 2025-09-02 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2f9b1a77a1c3"
down_revision: str | Sequence[str] | None = "d5a059a89aed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add status, relax nullables, add constraints, and pre-seed inventory rows."""
    # Columns
    op.add_column(
        "slot_assignments",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="available"),
    )
    op.alter_column(
        "slot_assignments",
        "text_storage_id",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.alter_column(
        "slot_assignments",
        "original_file_name",
        existing_type=sa.String(length=500),
        nullable=True,
    )

    # Normalize existing rows: mark assigned where content present
    op.execute("UPDATE slot_assignments SET status='assigned' WHERE text_storage_id IS NOT NULL")

    # Constraints and indexes
    op.create_check_constraint(
        "ck_slot_status_valid",
        "slot_assignments",
        "status IN ('available','assigned')",
    )
    op.create_unique_constraint(
        "uq_slot_unique_per_batch",
        "slot_assignments",
        ["batch_tracker_id", "internal_essay_id"],
    )
    op.create_index(
        "ix_slot_unique_content_assignment",
        "slot_assignments",
        ["batch_tracker_id", "text_storage_id"],
        unique=True,
        postgresql_where=sa.text("text_storage_id IS NOT NULL"),
    )
    op.create_index(
        "ix_slot_available_slots",
        "slot_assignments",
        ["batch_tracker_id", "status"],
        unique=False,
        postgresql_where=sa.text("status = 'available'"),
    )

    # Pre-seed inventory rows for all expected essay IDs
    op.execute(
        sa.text(
            """
            INSERT INTO slot_assignments (batch_tracker_id, internal_essay_id, status)
            SELECT bet.id, essay_id_text::text, 'available'
            FROM batch_essay_trackers AS bet
            CROSS JOIN json_array_elements_text(bet.expected_essay_ids) AS essay_id_text
            WHERE NOT EXISTS (
                SELECT 1 FROM slot_assignments sa
                WHERE sa.batch_tracker_id = bet.id
                  AND sa.internal_essay_id = essay_id_text::text
            )
            """
        )
    )


def downgrade() -> None:
    """Drop added constraints/columns and remove empty seeded rows."""
    # Remove rows that are clearly unassigned inventory (best-effort)
    op.execute(
        sa.text(
            "DELETE FROM slot_assignments WHERE status = 'available' AND text_storage_id IS NULL"
        )
    )

    # Indexes/constraints
    op.drop_index("ix_slot_available_slots", table_name="slot_assignments")
    op.drop_index("ix_slot_unique_content_assignment", table_name="slot_assignments")
    op.drop_constraint("uq_slot_unique_per_batch", "slot_assignments", type_="unique")
    op.drop_constraint("ck_slot_status_valid", "slot_assignments", type_="check")

    # Columns
    op.alter_column(
        "slot_assignments",
        "original_file_name",
        existing_type=sa.String(length=500),
        nullable=False,
    )
    op.alter_column(
        "slot_assignments",
        "text_storage_id",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.drop_column("slot_assignments", "status")

