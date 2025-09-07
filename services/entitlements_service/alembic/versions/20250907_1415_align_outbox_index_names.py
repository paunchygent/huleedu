"""Align outbox index names with shared library conventions

Revision ID: 20250907_align_outbox_indexes
Revises: a7754a58c81a
Create Date: 2025-09-07 14:15:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20250907_align_outbox_indexes"
down_revision: Union[str, Sequence[str], None] = "a7754a58c81a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename legacy outbox indexes to shared naming convention.

    - Drop: ix_outbox_unpublished, ix_outbox_aggregate
    - Create: ix_event_outbox_unpublished (partial), ix_event_outbox_aggregate
    """
    # Use raw SQL drops with IF EXISTS for idempotency
    op.execute("DROP INDEX IF EXISTS ix_outbox_unpublished")
    op.execute("DROP INDEX IF EXISTS ix_outbox_aggregate")

    # Create shared name indexes
    op.create_index(
        "ix_event_outbox_unpublished",
        "event_outbox",
        ["published_at", "created_at"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_index(
        "ix_event_outbox_aggregate",
        "event_outbox",
        ["aggregate_type", "aggregate_id"],
        unique=False,
    )


def downgrade() -> None:
    """Recreate legacy index names and drop shared ones."""
    # Drop new shared indexes
    op.execute("DROP INDEX IF EXISTS ix_event_outbox_unpublished")
    op.execute("DROP INDEX IF EXISTS ix_event_outbox_aggregate")

    # Recreate legacy aliases
    op.create_index(
        "ix_outbox_unpublished",
        "event_outbox",
        ["published_at", "topic", "created_at"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_index(
        "ix_outbox_aggregate",
        "event_outbox",
        ["aggregate_type", "aggregate_id"],
        unique=False,
    )
