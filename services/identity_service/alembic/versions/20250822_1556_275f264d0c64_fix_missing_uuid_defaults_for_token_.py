"""Fix missing UUID defaults for token tables primary keys

Revision ID: 275f264d0c64
Revises: 79f0cd9fc513
Create Date: 2025-08-22 15:56:02.247928

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "275f264d0c64"
down_revision: Union[str, None] = "79f0cd9fc513"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the migration."""
    # Add missing UUID default to email_verification_tokens.id column
    op.alter_column(
        "email_verification_tokens",
        "id",
        server_default=sa.text("gen_random_uuid()"),
        existing_type=sa.UUID(),
        existing_nullable=False,
    )
    
    # Add missing UUID default to password_reset_tokens.id column
    op.alter_column(
        "password_reset_tokens",
        "id",
        server_default=sa.text("gen_random_uuid()"),
        existing_type=sa.UUID(),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Revert the migration."""
    # Remove UUID default from password_reset_tokens.id column
    op.alter_column(
        "password_reset_tokens",
        "id",
        server_default=None,
        existing_type=sa.UUID(),
        existing_nullable=False,
    )
    
    # Remove UUID default from email_verification_tokens.id column
    op.alter_column(
        "email_verification_tokens",
        "id",
        server_default=None,
        existing_type=sa.UUID(),
        existing_nullable=False,
    )
