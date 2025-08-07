"""Add event outbox table for reliable event publishing

Revision ID: dd059078c9c5
Revises: 20250724_0003
Create Date: 2025-08-07 14:11:05.162509

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "dd059078c9c5"
down_revision: Union[str, None] = "20250724_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the migration."""
    # Create event_outbox table for transactional outbox pattern
    op.create_table(
        "event_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Unique identifier for the outbox entry",
        ),
        sa.Column(
            "aggregate_id",
            sa.String(length=255),
            nullable=False,
            comment="ID of the aggregate (batch_id, essay_id) that generated this event",
        ),
        sa.Column(
            "aggregate_type",
            sa.String(length=100),
            nullable=False,
            comment="Type of aggregate (batch, essay) for categorization",
        ),
        sa.Column(
            "event_type",
            sa.String(length=255),
            nullable=False,
            comment="Type/topic of the event (e.g., huleedu.ras.batch.results.ready.v1)",
        ),
        sa.Column(
            "event_data",
            sa.JSON(),
            nullable=False,
            comment="The complete event data as JSON (EventEnvelope)",
        ),
        sa.Column(
            "event_key",
            sa.String(length=255),
            nullable=True,
            comment="Kafka message key for partitioning",
        ),
        sa.Column(
            "topic",
            sa.String(length=255),
            nullable=False,
            comment="Kafka topic to publish to",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="When the event was created",
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the event was successfully published to Kafka",
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Number of publish attempts",
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
            comment="Last error message if publishing failed",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for efficient querying
    op.create_index(
        "ix_event_outbox_unpublished",
        "event_outbox",
        ["published_at", "created_at"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_index(
        op.f("ix_event_outbox_aggregate_id"),
        "event_outbox",
        ["aggregate_id"],
        unique=False,
    )


def downgrade() -> None:
    """Revert the migration."""
    # Drop indexes first
    op.drop_index(op.f("ix_event_outbox_aggregate_id"), table_name="event_outbox")
    op.drop_index("ix_event_outbox_unpublished", table_name="event_outbox")

    # Drop the table
    op.drop_table("event_outbox")
