"""Create stored_content table for Content Service.

Stores persistent content bytes referenced by other services.

Revision ID: 0001
Revises:
Create Date: 2025-11-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create stored_content table and indexes."""
    op.create_table(
        "stored_content",
        sa.Column("content_id", sa.String(length=32), primary_key=True, nullable=False),
        sa.Column("content_data", sa.LargeBinary(), nullable=False),
        sa.Column("content_size", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=False),
    )

    # Index to support time-based queries/cleanup
    op.create_index(
        "ix_stored_content_created_at",
        "stored_content",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop stored_content table and indexes."""
    op.drop_index("ix_stored_content_created_at", table_name="stored_content")
    op.drop_table("stored_content")
