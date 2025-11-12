"""merge heads

Revision ID: f8769bf24989
Revises: 59d16918f933, a1b2c3d4e5f6
Create Date: 2025-11-12 00:58:34.179406

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f8769bf24989"
down_revision: Union[str, Sequence[str], None] = ("59d16918f933", "a1b2c3d4e5f6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
