"""Add file_upload_id column for complete file traceability.

This migration adds file_upload_id to essay_results table to enable
complete traceability from file upload through assessment results.
Part of the File Service Client Traceability feature implementation.

Revision ID: 20250724_0003
Revises: 20250721_0002
Create Date: 2025-07-24
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20250724_0003"
down_revision = "20250721_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add file_upload_id column to essay_results table with index."""
    # Add file_upload_id column - nullable to maintain backward compatibility
    op.add_column(
        "essay_results",
        sa.Column("file_upload_id", sa.String(255), nullable=True),
    )

    # Create index for efficient lookups by file_upload_id
    op.create_index(
        "idx_essay_file_upload",
        "essay_results",
        ["file_upload_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove file_upload_id column and its index."""
    # Drop index first
    op.drop_index("idx_essay_file_upload", table_name="essay_results")

    # Drop column
    op.drop_column("essay_results", "file_upload_id")
