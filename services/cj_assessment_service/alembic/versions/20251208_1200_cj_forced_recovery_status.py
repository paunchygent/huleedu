"""Add COMPLETE_FORCED_RECOVERY to cj_batch_status_enum

Revision ID: cj_forced_recovery_status
Revises: 2ea57f0f8b9d
Create Date: 2025-12-08 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cj_forced_recovery_status"
down_revision: Union[str, Sequence[str], None] = "2ea57f0f8b9d"
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
              AND e.enumlabel = 'COMPLETE_FORCED_RECOVERY'
          ) THEN
            ALTER TYPE cj_batch_status_enum ADD VALUE 'COMPLETE_FORCED_RECOVERY';
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """No-op: Removing enum values is not supported safely in Postgres."""
    pass
