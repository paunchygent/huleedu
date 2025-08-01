"""Remove deprecated skill_level field from courses table

Revision ID: 8ad1e604aea6
Revises: 0002
Create Date: 2025-08-01 15:36:57.416014

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8ad1e604aea6"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove deprecated skill_level field now handled by domain enums."""
    op.drop_column("courses", "skill_level")


def downgrade() -> None:
    """Restore deprecated skill_level field for rollback safety."""
    op.add_column(
        "courses", sa.Column("skill_level", sa.Integer(), nullable=False, server_default="1")
    )
