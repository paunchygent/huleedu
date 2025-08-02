"""Add class_id column to batches table for GUEST vs REGULAR batch differentiation

Revision ID: add_class_id_to_batches
Revises: fd6447293cdb
Create Date: 2025-08-01 15:30:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "add_class_id_to_batches"
down_revision = "fd6447293cdb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add class_id column to batches table."""
    # Add class_id column
    op.add_column(
        "batches",
        sa.Column(
            "class_id",
            sa.String(255),
            nullable=True,
            comment=(
                "Class ID for REGULAR batches requiring student matching, NULL for GUEST batches"
            ),
        ),
    )

    # Add index for class_id lookups
    op.create_index("ix_batches_class_id", "batches", ["class_id"])


def downgrade() -> None:
    """Remove class_id column from batches table."""
    # Drop index first
    op.drop_index("ix_batches_class_id", table_name="batches")

    # Drop column
    op.drop_column("batches", "class_id")
