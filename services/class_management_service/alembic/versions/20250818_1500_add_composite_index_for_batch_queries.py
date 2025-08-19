"""Add composite index for efficient batch student name queries

Revision ID: a1b2c3d4e5f6
Revises: 20ba9223a723
Create Date: 2025-08-18 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "20ba9223a723"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add composite index for efficient batch student name queries
    # This supports the Phase 3 requirement for ≤ 50ms batch queries
    op.create_index(
        "ix_essay_student_associations_batch_essay_composite",
        "essay_student_associations",
        ["batch_id", "essay_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove the composite index
    op.drop_index(
        "ix_essay_student_associations_batch_essay_composite",
        table_name="essay_student_associations",
    )
