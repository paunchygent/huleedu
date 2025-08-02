"""Remove legacy fields from batch_essay_trackers

Revision ID: f0efbf460136
Revises: 20250724_0001
Create Date: 2025-08-01 15:03:27.242135

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f0efbf460136"
down_revision: str | Sequence[str] | None = "20250724_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove legacy fields that are now handled by Redis-based state management."""
    # Drop legacy columns that are replaced by Redis operations
    op.drop_column("batch_essay_trackers", "total_slots")
    op.drop_column("batch_essay_trackers", "assigned_slots")
    op.drop_column("batch_essay_trackers", "is_ready")


def downgrade() -> None:
    """Restore legacy fields for rollback safety."""
    # Add back legacy fields with proper defaults for rollback
    op.add_column(
        "batch_essay_trackers",
        sa.Column("total_slots", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "batch_essay_trackers",
        sa.Column("assigned_slots", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "batch_essay_trackers",
        sa.Column("is_ready", sa.Boolean(), nullable=False, server_default="false"),
    )
