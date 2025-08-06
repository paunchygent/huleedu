"""Add file_uploads table for user attribution

Revision ID: 20250106_0001
Revises: 20250725_0001
Create Date: 2025-01-06 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20250106_0001"
down_revision: Union[str, None] = "20250725_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create file_uploads table to track file uploads with user attribution."""
    op.create_table(
        "file_uploads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("file_upload_id", sa.String(255), nullable=False),
        sa.Column("batch_id", sa.String(255), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("raw_file_storage_id", sa.String(255), nullable=True),
        sa.Column("text_storage_id", sa.String(255), nullable=True),
        sa.Column("processing_status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("validation_error_code", sa.String(100), nullable=True),
        sa.Column("validation_error_message", sa.Text(), nullable=True),
        sa.Column(
            "upload_timestamp",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("processed_timestamp", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_upload_id"),
    )

    # Create indexes for common queries
    op.create_index("ix_file_uploads_batch_id", "file_uploads", ["batch_id"])
    op.create_index("ix_file_uploads_user_id", "file_uploads", ["user_id"])
    op.create_index("ix_file_uploads_processing_status", "file_uploads", ["processing_status"])
    op.create_index("ix_file_uploads_upload_timestamp", "file_uploads", ["upload_timestamp"])

    # Composite index for batch + user queries
    op.create_index("ix_file_uploads_batch_user", "file_uploads", ["batch_id", "user_id"])


def downgrade() -> None:
    """Drop file_uploads table and its indexes."""
    op.drop_index("ix_file_uploads_batch_user", table_name="file_uploads")
    op.drop_index("ix_file_uploads_upload_timestamp", table_name="file_uploads")
    op.drop_index("ix_file_uploads_processing_status", table_name="file_uploads")
    op.drop_index("ix_file_uploads_user_id", table_name="file_uploads")
    op.drop_index("ix_file_uploads_batch_id", table_name="file_uploads")
    op.drop_table("file_uploads")
