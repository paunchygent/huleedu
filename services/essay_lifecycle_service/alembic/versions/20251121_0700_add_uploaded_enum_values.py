"""Add uploaded and text_extracted to essay_status_enum

Revision ID: d3e5f8a9b1c2
Revises: c2d4e6f7a8b9
Create Date: 2025-11-21 07:00:00.000000

This migration adds 'uploaded' and 'text_extracted' enum values to essay_status_enum
to support essay creation with initial upload status before content extraction.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3e5f8a9b1c2"
down_revision: str = "c2d4e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add 'uploaded' and 'text_extracted' enum values to essay_status_enum.

    Uses ADD VALUE IF NOT EXISTS for idempotency (PostgreSQL 9.6+).
    """
    op.execute(
        sa.text(
            """
            ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'uploaded';
            """
        )
    )
    op.execute(
        sa.text(
            """
            ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'text_extracted';
            """
        )
    )


def downgrade() -> None:
    """PostgreSQL does not support removing enum values.

    Downgrading would require:
    1. Creating new enum type without the values
    2. Migrating all data to new type
    3. Dropping old type and renaming new type

    This is complex and risky, so downgrade is not supported.
    If needed, create a new forward migration to handle cleanup.
    """
    raise NotImplementedError(
        "Removing enum values is not supported. Create a forward migration if cleanup is needed."
    )
