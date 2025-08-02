"""Add student association fields to essays

Revision ID: 0fe611529ef2
Revises: f0efbf460136
Create Date: 2025-08-02 11:38:47.033346

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0fe611529ef2"
down_revision: str | Sequence[str] | None = "f0efbf460136"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add student association fields to support NLP Phase 1 student matching."""
    # Add student association fields to essay_states table
    op.add_column(
        "essay_states",
        sa.Column("student_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "essay_states",
        sa.Column("association_confirmed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "essay_states",
        sa.Column("association_method", sa.String(50), nullable=True),
    )

    # Create index on student_id for efficient lookups
    op.create_index(
        "idx_essay_states_student_id",
        "essay_states",
        ["student_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove student association fields."""
    # Drop index first
    op.drop_index("idx_essay_states_student_id", table_name="essay_states")

    # Drop columns
    op.drop_column("essay_states", "association_method")
    op.drop_column("essay_states", "association_confirmed_at")
    op.drop_column("essay_states", "student_id")
