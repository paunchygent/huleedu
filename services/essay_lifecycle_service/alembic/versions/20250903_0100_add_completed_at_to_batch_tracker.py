"""Add completed_at to batch_essay_trackers for completion marking

Revision ID: 7b4f3c2210d1
Revises: 4a7c2c11b9e0
Create Date: 2025-09-03 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b4f3c2210d1"
down_revision: str | Sequence[str] | None = "4a7c2c11b9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "batch_essay_trackers",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("batch_essay_trackers", "completed_at")

