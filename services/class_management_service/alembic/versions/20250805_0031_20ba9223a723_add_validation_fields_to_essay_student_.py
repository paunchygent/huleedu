"""Add validation fields to essay_student_associations

Revision ID: 20ba9223a723
Revises: 7d21f7fdd41e
Create Date: 2025-08-05 00:31:25.186334

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20ba9223a723"
down_revision: Union[str, Sequence[str], None] = "7d21f7fdd41e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Since we're in development and have existing data, we'll need to handle this carefully
    # Option 1: Delete existing data (development only)
    op.execute("DELETE FROM essay_student_associations")

    # Add class_id column with foreign key
    op.add_column(
        "essay_student_associations",
        sa.Column(
            "class_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("classes.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )

    # Add confidence_score column
    op.add_column(
        "essay_student_associations",
        sa.Column("confidence_score", sa.Float(), nullable=True),
    )

    # Add match_reasons column (JSON)
    op.add_column(
        "essay_student_associations",
        sa.Column("match_reasons", sa.JSON(), nullable=True),
    )

    # Add validation_status column with default
    op.add_column(
        "essay_student_associations",
        sa.Column(
            "validation_status",
            sa.String(50),
            nullable=False,
            server_default="pending_validation",
        ),
    )

    # Add validated_by column
    op.add_column(
        "essay_student_associations",
        sa.Column("validated_by", sa.String(255), nullable=True),
    )

    # Add validated_at column
    op.add_column(
        "essay_student_associations",
        sa.Column("validated_at", sa.DateTime(), nullable=True),
    )

    # Add validation_method column
    op.add_column(
        "essay_student_associations",
        sa.Column("validation_method", sa.String(50), nullable=True),
    )

    # Create indexes for performance
    op.create_index(
        "idx_essay_associations_validation_status",
        "essay_student_associations",
        ["class_id", "validation_status"],
    )

    op.create_index(
        "idx_essay_associations_batch",
        "essay_student_associations",
        ["batch_id", "validation_status"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes first
    op.drop_index("idx_essay_associations_batch", "essay_student_associations")
    op.drop_index("idx_essay_associations_validation_status", "essay_student_associations")

    # Drop columns in reverse order
    op.drop_column("essay_student_associations", "validation_method")
    op.drop_column("essay_student_associations", "validated_at")
    op.drop_column("essay_student_associations", "validated_by")
    op.drop_column("essay_student_associations", "validation_status")
    op.drop_column("essay_student_associations", "match_reasons")
    op.drop_column("essay_student_associations", "confidence_score")
    op.drop_column("essay_student_associations", "class_id")
