"""Add unique constraint to prevent duplicate unpublished completion events

This migration adds a partial unique index on event_outbox to prevent duplicate
unpublished completion events for the same aggregate_id and event_type. The partial
index only applies to unpublished events (published_at IS NULL), allowing the same
event to appear multiple times in the audit trail after publication.

Revision ID: 20251121_1800
Revises: 20251119_1200
Create Date: 2025-11-21 18:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251121_1800"
down_revision: Union[str, None] = "20251119_1200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add partial unique index on unpublished outbox events.

    This prevents duplicate completion events from being published when multiple
    triggers fire for the same batch. The index is partial (WHERE published_at IS NULL)
    so it only prevents duplicates in the unpublished queue, not in the audit trail.
    """
    # First, clean up any existing duplicate unpublished rows
    # Keep the oldest unpublished event for each (aggregate_id, event_type) pair
    op.execute(
        """
        DELETE FROM event_outbox
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                    ROW_NUMBER() OVER (
                        PARTITION BY aggregate_id, event_type
                        ORDER BY created_at ASC
                    ) as row_num
                FROM event_outbox
                WHERE published_at IS NULL
            ) duplicates
            WHERE row_num > 1
        )
        """
    )

    # Create partial unique index on unpublished events
    op.create_index(
        "idx_outbox_unique_unpublished",
        "event_outbox",
        ["aggregate_id", "event_type"],
        unique=True,
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    """Remove partial unique index on unpublished outbox events."""
    op.drop_index(
        "idx_outbox_unique_unpublished",
        table_name="event_outbox",
        postgresql_where=sa.text("published_at IS NULL"),
    )
