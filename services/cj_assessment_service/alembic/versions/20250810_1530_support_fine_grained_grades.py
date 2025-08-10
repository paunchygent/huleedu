"""Support fine-grained 15-point grade scale

Revision ID: support_fine_grained_grades
Revises: 9e960c702447
Create Date: 2025-08-10 15:30:00.000000

This migration updates the schema to support fine-grained grades (A, A-, B+, B, B-, etc.)
by extending grade field lengths from 3 to 4 characters to accommodate the +/- modifiers.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "support_fine_grained_grades"
down_revision: Union[str, None] = "9e960c702447"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Extend grade fields to support fine-grained grades with +/- modifiers."""

    # Update anchor_essay_references.grade to support fine grades
    op.alter_column(
        "anchor_essay_references",
        "grade",
        type_=sa.String(4),
        existing_type=sa.String(3),
        existing_nullable=False,
        comment="Fine-grained grade (e.g., A, A-, B+, B, B-, C+, etc.)",
    )

    # Update grade_projections.primary_grade to support fine grades
    op.alter_column(
        "grade_projections",
        "primary_grade",
        type_=sa.String(4),
        existing_type=sa.String(3),
        existing_nullable=False,
        comment="Fine-grained primary grade assigned to the essay",
    )


def downgrade() -> None:
    """Revert grade fields to original 3-character length."""

    # Note: This downgrade may fail if any existing data contains fine grades
    # You should clean data before downgrading

    # Revert grade_projections.primary_grade
    op.alter_column(
        "grade_projections",
        "primary_grade",
        type_=sa.String(3),
        existing_type=sa.String(4),
        existing_nullable=False,
        comment=None,
    )

    # Revert anchor_essay_references.grade
    op.alter_column(
        "anchor_essay_references",
        "grade",
        type_=sa.String(3),
        existing_type=sa.String(4),
        existing_nullable=False,
        comment=None,
    )
