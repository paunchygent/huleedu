"""Add org_id column to batch_essay_trackers for credit attribution

Revision ID: d5a059a89aed
Revises: 106e57a84619
Create Date: 2025-08-31 11:26:09.064893

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5a059a89aed"
down_revision: str | Sequence[str] | None = "106e57a84619"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add org_id column to batch_essay_trackers table."""
    op.add_column("batch_essay_trackers", sa.Column("org_id", sa.String(255), nullable=True))


def downgrade() -> None:
    """Remove org_id column from batch_essay_trackers table."""
    op.drop_column("batch_essay_trackers", "org_id")
