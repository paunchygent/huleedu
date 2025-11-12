"""fix_error_timestamp_timezone_support

Revision ID: d03b409524ae
Revises: d3f4e5f6a7b8
Create Date: 2025-07-17 01:31:11.667825

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d03b409524ae"
down_revision: Union[str, Sequence[str], None] = "d3f4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        sa.text(
            """
            ALTER TABLE cj_comparison_pairs
                ADD COLUMN IF NOT EXISTS request_correlation_id UUID;
            """
        )
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE cj_comparison_pairs
                ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ;
            """
        )
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE cj_comparison_pairs
                ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
            """
        )
    )
    op.alter_column(
        "cj_comparison_pairs",
        "error_timestamp",
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_cj_comparison_pairs_request_correlation_id
                ON cj_comparison_pairs (request_correlation_id);
            """
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS ix_cj_comparison_pairs_request_correlation_id;
            """
        )
    )
    op.alter_column(
        "cj_comparison_pairs",
        "error_timestamp",
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        existing_nullable=True,
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE cj_comparison_pairs
                DROP COLUMN IF EXISTS completed_at;
            """
        )
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE cj_comparison_pairs
                DROP COLUMN IF EXISTS submitted_at;
            """
        )
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE cj_comparison_pairs
                DROP COLUMN IF EXISTS request_correlation_id;
            """
        )
    )
