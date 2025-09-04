"""Add COMPLETE_INSUFFICIENT_ESSAYS to cj_batch_status_enum

Revision ID: cj_insufficient_essays_status
Revises: baf9cf9c8c5c
Create Date: 2025-09-01 19:05:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cj_insufficient_essays_status"
down_revision: Union[str, Sequence[str], None] = "baf9cf9c8c5c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add new enum value to cj_batch_status_enum."""
    op.execute(
        """
        DO $$ BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM pg_type t
            JOIN pg_enum e ON t.oid = e.enumtypid
            WHERE t.typname = 'cj_batch_status_enum'
              AND e.enumlabel = 'COMPLETE_INSUFFICIENT_ESSAYS'
          ) THEN
            ALTER TYPE cj_batch_status_enum ADD VALUE 'COMPLETE_INSUFFICIENT_ESSAYS';
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """No-op: Removing enum values is not supported safely in Postgres."""
    pass
