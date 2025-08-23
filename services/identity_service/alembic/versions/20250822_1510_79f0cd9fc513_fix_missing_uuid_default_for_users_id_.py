"""fix missing UUID default for users.id column

Revision ID: 79f0cd9fc513
Revises: 5c38467d2203
Create Date: 2025-08-22 15:10:14.381632

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "79f0cd9fc513"
down_revision: Union[str, None] = "5c38467d2203"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the migration."""
    # Add missing UUID default to users.id column
    op.alter_column(
        "users",
        "id",
        server_default=sa.text("gen_random_uuid()"),
        existing_type=sa.UUID(),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Revert the migration."""
    # Remove UUID default from users.id column
    op.alter_column(
        "users",
        "id",
        server_default=None,
        existing_type=sa.UUID(),
        existing_nullable=False,
    )
