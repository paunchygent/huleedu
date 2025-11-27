"""Add assignment_id and text_storage_id indexes to file_uploads

Revision ID: 20251127_1200
Revises: 4073c6627a50
Create Date: 2025-11-27 12:00:00.000000

Adds assignment_id column for traceability and indexes text_storage_id for
fast joins between CJ results and uploaded files.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251127_1200"
down_revision: Union[str, None] = "4073c6627a50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add assignment_id column and supporting indexes for lookups."""

    op.add_column(
        "file_uploads",
        sa.Column(
            "assignment_id",
            sa.String(length=255),
            nullable=True,
            comment="Optional assignment identifier for traceability",
        ),
    )
    op.create_index(
        "ix_file_uploads_assignment_id",
        "file_uploads",
        ["assignment_id"],
        unique=False,
    )
    op.create_index(
        "ix_file_uploads_text_storage_id",
        "file_uploads",
        ["text_storage_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove assignment_id column and indexes."""

    op.drop_index("ix_file_uploads_text_storage_id", table_name="file_uploads")
    op.drop_index("ix_file_uploads_assignment_id", table_name="file_uploads")
    op.drop_column("file_uploads", "assignment_id")
