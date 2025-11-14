"""Add anchor_label and label-based unique constraint for anchors.

Revision ID: 20251114_0900
Revises: 20251114_0230
Create Date: 2025-11-14 09:00:00.000000

This migration introduces filename-based identity for anchor essays by:
- Adding an anchor_label column to anchor_essay_references
- Backfilling existing rows with synthetic labels
- Replacing the (assignment_id, grade, grade_scale) unique constraint with
  (assignment_id, anchor_label, grade_scale)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20251114_0900"
down_revision: Union[str, Sequence[str], None] = "20251114_0230"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add anchor_label column and label-based uniqueness constraint."""
    # 1) Add anchor_label as nullable to allow backfill
    op.add_column(
        "anchor_essay_references",
        sa.Column("anchor_label", sa.String(length=255), nullable=True),
    )

    # 2) Backfill existing rows with deterministic synthetic labels
    #    using grade and id to ensure uniqueness per row.
    op.execute(
        """
        UPDATE anchor_essay_references
        SET anchor_label = CONCAT('grade_', grade, '_id_', id)
        WHERE anchor_label IS NULL
        """
    )

    # 3) Make anchor_label non-nullable now that all rows have a value
    op.alter_column(
        "anchor_essay_references",
        "anchor_label",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    # 4) Drop the old grade-based unique constraint if it exists
    op.drop_constraint(
        "uq_anchor_assignment_grade_scale",
        "anchor_essay_references",
        type_="unique",
    )

    # 5) Create new label-based unique constraint
    op.create_unique_constraint(
        "uq_anchor_assignment_label_scale",
        "anchor_essay_references",
        ["assignment_id", "anchor_label", "grade_scale"],
    )

    # 6) Create index on anchor_label to match ORM index=True
    op.create_index(
        op.f("ix_anchor_essay_references_anchor_label"),
        "anchor_essay_references",
        ["anchor_label"],
        unique=False,
    )


def downgrade() -> None:
    """Revert label-based uniqueness back to grade-based constraint."""
    # 1) Drop label-based unique constraint and index
    op.drop_constraint(
        "uq_anchor_assignment_label_scale",
        "anchor_essay_references",
        type_="unique",
    )
    op.drop_index(
        op.f("ix_anchor_essay_references_anchor_label"),
        table_name="anchor_essay_references",
    )

    # 2) Drop anchor_label column
    op.drop_column("anchor_essay_references", "anchor_label")

    # 3) Restore the original grade-based unique constraint
    op.create_unique_constraint(
        "uq_anchor_assignment_grade_scale",
        "anchor_essay_references",
        ["assignment_id", "grade", "grade_scale"],
    )
