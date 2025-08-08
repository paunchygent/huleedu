"""Add explicit topic column to event outbox

Revision ID: 106e57a84619
Revises: 0fe611529ef2
Create Date: 2025-08-08 10:45:49.359479

Migration to add explicit topic column to event_outbox table for better performance
and consistency with CJ Assessment Service pattern. Extracts topic from existing
JSON event_data and creates indexed column for efficient queries.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "106e57a84619"
down_revision: str | Sequence[str] | None = "0fe611529ef2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add explicit topic column and migrate data from JSON."""

    # Step 1: Add topic column as nullable initially
    op.add_column(
        "event_outbox",
        sa.Column(
            "topic",
            sa.String(255),
            nullable=True,
            comment="Kafka topic to publish to",
        ),
    )

    # Step 2: Extract topic from existing JSON event_data and populate the column
    # Use PostgreSQL JSON extraction to get topic from event_data
    op.execute(
        """
        UPDATE event_outbox
        SET topic = event_data->>'topic'
        WHERE topic IS NULL AND event_data->>'topic' IS NOT NULL
        """
    )

    # Step 3: Set default topic for any records that don't have topic in JSON
    # This handles edge cases where old records might not have topic embedded
    op.execute(
        """
        UPDATE event_outbox
        SET topic = COALESCE(
            event_data->>'topic',
            'huleedu.essay_lifecycle.unknown.v1'
        )
        WHERE topic IS NULL
        """
    )

    # Step 4: Make topic column NOT NULL now that all rows have values
    op.alter_column(
        "event_outbox",
        "topic",
        nullable=False,
    )

    # Step 5: Add index on topic column for efficient filtering and queries
    op.create_index(
        "ix_event_outbox_topic",
        "event_outbox",
        ["topic"],
        unique=False,
    )

    # Step 6: Add composite index for efficient relay worker queries
    # This replaces the old unpublished index with topic-aware version
    op.drop_index("idx_outbox_unpublished", table_name="event_outbox")
    op.create_index(
        "ix_event_outbox_unpublished_topic",
        "event_outbox",
        ["published_at", "topic", "created_at"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    """Remove explicit topic column and restore original indexes."""

    # Step 1: Restore original unpublished index
    op.drop_index("ix_event_outbox_unpublished_topic", table_name="event_outbox")
    op.create_index(
        "idx_outbox_unpublished",
        "event_outbox",
        ["published_at"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )

    # Step 2: Drop topic-specific index
    op.drop_index("ix_event_outbox_topic", table_name="event_outbox")

    # Step 3: Drop the topic column
    # Note: This will lose the explicit topic data, but it should still be
    # available in the JSON event_data field
    op.drop_column("event_outbox", "topic")
