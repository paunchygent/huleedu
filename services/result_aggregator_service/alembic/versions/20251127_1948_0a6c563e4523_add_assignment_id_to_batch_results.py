"""add_assignment_id_to_batch_results

Revision ID: 0a6c563e4523
Revises: 98937098c40a
Create Date: 2025-11-27 19:48:02.251903

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0a6c563e4523"
down_revision: Union[str, None] = "98937098c40a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the migration."""
    # Add nullable assignment_id column for batch-level assignment tracking
    op.add_column("batch_results", sa.Column("assignment_id", sa.String(length=100), nullable=True))
    # Create index to support assignment-driven queries and reporting
    op.create_index(
        "ix_batch_results_assignment_id",
        "batch_results",
        ["assignment_id"],
        unique=False,
    )


def downgrade() -> None:
    """Revert the migration."""
    # Drop assignment_id index and column
    op.drop_index("ix_batch_results_assignment_id", table_name="batch_results")
    op.drop_column("batch_results", "assignment_id")
