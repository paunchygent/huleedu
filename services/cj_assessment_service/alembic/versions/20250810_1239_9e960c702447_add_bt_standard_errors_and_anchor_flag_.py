"""Add BT standard errors and anchor flag to ProcessedEssay

Revision ID: 9e960c702447
Revises: e2c5e2b6606b
Create Date: 2025-08-10 12:39:50.055782

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9e960c702447"
down_revision: Union[str, Sequence[str], None] = "e2c5e2b6606b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add current_bt_se column for Bradley-Terry standard errors
    op.add_column(
        "cj_processed_essays",
        sa.Column("current_bt_se", sa.Float(), nullable=True),
    )

    # Add is_anchor column to identify anchor essays
    op.add_column(
        "cj_processed_essays",
        sa.Column(
            "is_anchor",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("cj_processed_essays", "is_anchor")
    op.drop_column("cj_processed_essays", "current_bt_se")
