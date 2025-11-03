"""add_grade_scale_columns

Adds grade_scale columns to anchor_essay_references and grade_projections
tables to support multiple grade scales (Swedish 8-anchor, ENG5 NP variants).

Revision ID: bf559b4a86bf
Revises: cj_insufficient_essays_status
Create Date: 2025-11-03 22:22:04.468220

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bf559b4a86bf"
down_revision: Union[str, Sequence[str], None] = "cj_insufficient_essays_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add grade_scale columns to support multiple grade scales.

    Tables updated:
    - anchor_essay_references: Add grade_scale column with index
    - grade_projections: Add grade_scale column with index

    Default value 'swedish_8_anchor' ensures backward compatibility
    with existing data.
    """
    # Add grade_scale to anchor_essay_references
    op.add_column(
        "anchor_essay_references",
        sa.Column(
            "grade_scale",
            sa.String(length=50),
            nullable=False,
            server_default="swedish_8_anchor",
            comment="Grade scale identifier (swedish_8_anchor, eng5_np_legacy_9_step, eng5_np_national_9_step)",
        ),
    )
    op.create_index(
        op.f("ix_anchor_essay_references_grade_scale"),
        "anchor_essay_references",
        ["grade_scale"],
        unique=False,
    )

    # Add grade_scale to grade_projections
    op.add_column(
        "grade_projections",
        sa.Column(
            "grade_scale",
            sa.String(length=50),
            nullable=False,
            server_default="swedish_8_anchor",
            comment="Grade scale used for this projection",
        ),
    )
    op.create_index(
        op.f("ix_grade_projections_grade_scale"),
        "grade_projections",
        ["grade_scale"],
        unique=False,
    )


def downgrade() -> None:
    """
    Remove grade_scale columns from anchor and projection tables.

    WARNING: This will lose grade_scale information for any non-Swedish
    anchors/projections in the database.
    """
    # Drop indexes first
    op.drop_index(
        op.f("ix_grade_projections_grade_scale"), table_name="grade_projections"
    )
    op.drop_index(
        op.f("ix_anchor_essay_references_grade_scale"),
        table_name="anchor_essay_references",
    )

    # Drop columns
    op.drop_column("grade_projections", "grade_scale")
    op.drop_column("anchor_essay_references", "grade_scale")
