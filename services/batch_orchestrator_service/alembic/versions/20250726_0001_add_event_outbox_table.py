"""Add event outbox table for Transactional Outbox Pattern

Revision ID: 20250726_0001
Revises: 20250706_0001
Create Date: 2025-07-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20250726_0001"
down_revision: Union[str, None] = "20250706_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the event_outbox table and indexes."""
    # Create event_outbox table
    op.create_table(
        "event_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
            comment="Unique identifier for the outbox entry",
        ),
        sa.Column(
            "aggregate_id",
            sa.String(255),
            nullable=False,
            comment="ID of the aggregate this event relates to",
        ),
        sa.Column(
            "aggregate_type",
            sa.String(100),
            nullable=False,
            comment="Type of aggregate (e.g., 'batch', 'pipeline')",
        ),
        sa.Column(
            "event_type",
            sa.String(255),
            nullable=False,
            comment="Type of the event (e.g., 'huleedu.batch.spellcheck.initiate.command.v1')",
        ),
        sa.Column(
            "event_data",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            comment="JSON payload containing the full event envelope including topic",
        ),
        sa.Column(
            "event_key",
            sa.String(255),
            nullable=True,
            comment="Optional key for Kafka partitioning",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Timestamp when the event was created",
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when the event was successfully published",
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Number of publication attempts",
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
            comment="Last error message if publication failed",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Event outbox table for reliable event publishing to Kafka",
    )

    # Create indexes for efficient querying

    # Index for polling unpublished events (partial index)
    op.create_index(
        "ix_event_outbox_unpublished",
        "event_outbox",
        ["published_at", "created_at"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )

    # Index for looking up events by aggregate
    op.create_index(
        "ix_event_outbox_aggregate",
        "event_outbox",
        ["aggregate_type", "aggregate_id"],
        unique=False,
    )

    # Index for monitoring/debugging by event type
    op.create_index(
        "ix_event_outbox_event_type",
        "event_outbox",
        ["event_type"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the event_outbox table and indexes."""
    # Drop indexes first
    op.drop_index("ix_event_outbox_event_type", table_name="event_outbox")
    op.drop_index("ix_event_outbox_aggregate", table_name="event_outbox")
    op.drop_index("ix_event_outbox_unpublished", table_name="event_outbox")

    # Drop table
    op.drop_table("event_outbox")
