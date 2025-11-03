"""add_grade_scale_to_instructions

Add grade_scale column to assessment_instructions table to capture
assignment-specific grading scale metadata used across the CJ pipeline.

Revision ID: f83f2988a7c2
Revises: bf559b4a86bf
Create Date: 2025-11-03 23:05:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f83f2988a7c2"
down_revision: Union[str, Sequence[str], None] = "bf559b4a86bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add grade_scale column and supporting index to assessment_instructions."""
    op.add_column(
        "assessment_instructions",
        sa.Column(
            "grade_scale",
            sa.String(length=50),
            nullable=False,
            server_default="swedish_8_anchor",
            comment="Grade scale identifier associated with the assignment",
        ),
    )
    op.create_index(
        op.f("ix_assessment_instructions_grade_scale"),
        "assessment_instructions",
        ["grade_scale"],
        unique=False,
    )


def downgrade() -> None:
    """Remove grade_scale column and index from assessment_instructions."""
    op.drop_index(
        op.f("ix_assessment_instructions_grade_scale"),
        table_name="assessment_instructions",
    )
    op.drop_column("assessment_instructions", "grade_scale")
