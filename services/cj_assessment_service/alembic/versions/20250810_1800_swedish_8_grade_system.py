"""Implement Swedish 8-grade assessment system

Consolidates all schema changes needed for the Swedish grading system:
- Bradley-Terry standard errors and anchor identification
- Extended grade fields (4 chars) for minus grades
- Population priors for unbiased calibration

Revision ID: swedish_8_grade_system
Revises: e2c5e2b6606b
Create Date: 2025-08-10 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "swedish_8_grade_system"
down_revision: Union[str, Sequence[str], None] = "e2c5e2b6606b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply Swedish 8-grade system schema changes."""

    # 1. Add Bradley-Terry standard errors to processed essays
    op.add_column(
        "cj_processed_essays",
        sa.Column("current_bt_se", sa.Float(), nullable=True),
    )

    # 2. Add anchor essay flag
    op.add_column(
        "cj_processed_essays",
        sa.Column(
            "is_anchor",
            sa.Boolean(),
            nullable=False,
            server_default=text("FALSE"),
        ),
    )

    # 3. Extend grade fields to support Swedish system (includes minus grades like A-, B+)
    # Update anchor_essay_references.grade
    op.alter_column(
        "anchor_essay_references",
        "grade",
        type_=sa.String(4),
        existing_type=sa.String(3),
        existing_nullable=False,
        postgresql_using="grade::varchar(4)",
        comment="Swedish grade (e.g., A, A-, B, B-, C+, C, C-, D+, D, D-, E, E-, F)",
    )

    # Update grade_projections.primary_grade
    op.alter_column(
        "grade_projections",
        "primary_grade",
        type_=sa.String(4),
        existing_type=sa.String(3),
        existing_nullable=False,
        postgresql_using="primary_grade::varchar(4)",
        comment="Swedish primary grade assigned to the essay",
    )

    # 4. Add population prior support for unbiased calibration
    op.add_column(
        "grade_projections",
        sa.Column(
            "population_prior",
            sa.Float(),
            nullable=True,
            comment="Population-based prior probability for this grade",
        ),
    )

    # 5. Update any existing grade projection metadata to indicate Swedish system
    # Skip this update as we're in development with test data only
    # The application will set the correct metadata for new projections

    # 6. Create index for efficient anchor lookups
    op.create_index(
        "idx_cj_processed_essays_anchor",
        "cj_processed_essays",
        ["is_anchor"],
        postgresql_where=text("is_anchor = TRUE"),
    )


def downgrade() -> None:
    """Revert Swedish 8-grade system changes.

    WARNING: This may fail if data contains Swedish grades.
    Consider cleaning data before downgrading.
    """

    # Remove anchor index
    op.drop_index("idx_cj_processed_essays_anchor", "cj_processed_essays")

    # Remove population prior column
    op.drop_column("grade_projections", "population_prior")

    # Revert grade fields to 3 characters
    # This will fail if any grades use minus/plus modifiers
    op.alter_column(
        "grade_projections",
        "primary_grade",
        type_=sa.String(3),
        existing_type=sa.String(4),
        existing_nullable=False,
        postgresql_using="CASE WHEN LENGTH(primary_grade) > 3 THEN LEFT(primary_grade, 1) ELSE primary_grade END",
        comment=None,
    )

    op.alter_column(
        "anchor_essay_references",
        "grade",
        type_=sa.String(3),
        existing_type=sa.String(4),
        existing_nullable=False,
        postgresql_using="CASE WHEN LENGTH(grade) > 3 THEN LEFT(grade, 1) ELSE grade END",
        comment=None,
    )

    # Remove anchor flag
    op.drop_column("cj_processed_essays", "is_anchor")

    # Remove BT standard error
    op.drop_column("cj_processed_essays", "current_bt_se")
