"""Clean refactor: Replace error_message fields with error_detail JSON columns.

This is a CLEAN refactor with NO backwards compatibility.
Old error_message fields are removed completely in favor of structured error_detail.

Revision ID: 20250721_0002
Revises: 20250706_0001
Create Date: 2025-07-21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20250721_0002"
down_revision = "20250706_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Replace error_message string fields with error_detail JSON columns."""
    # Add new error_detail JSON columns
    op.add_column(
        "batch_results",
        sa.Column("batch_error_detail", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )

    op.add_column(
        "essay_results",
        sa.Column("spellcheck_error_detail", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "essay_results",
        sa.Column(
            "cj_assessment_error_detail", postgresql.JSON(astext_type=sa.Text()), nullable=True
        ),
    )

    # Drop the old error_message string fields - CLEAN refactor, no backwards compatibility
    op.drop_column("batch_results", "last_error")
    op.drop_column("essay_results", "spellcheck_error")
    op.drop_column("essay_results", "cj_assessment_error")


def downgrade() -> None:
    """Restore error_message string fields and remove error_detail JSON columns."""
    # Re-add the old string fields
    op.add_column(
        "batch_results",
        sa.Column("last_error", sa.String(500), nullable=True),
    )
    op.add_column(
        "essay_results",
        sa.Column("spellcheck_error", sa.String(500), nullable=True),
    )
    op.add_column(
        "essay_results",
        sa.Column("cj_assessment_error", sa.String(500), nullable=True),
    )

    # Drop the new JSON fields
    op.drop_column("essay_results", "cj_assessment_error_detail")
    op.drop_column("essay_results", "spellcheck_error_detail")
    op.drop_column("batch_results", "batch_error_detail")
