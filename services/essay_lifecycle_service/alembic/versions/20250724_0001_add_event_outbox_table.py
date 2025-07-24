"""Add event outbox table for transactional outbox pattern

Revision ID: 20250724_0001
Revises: c15f023f2624
Create Date: 2025-07-24 21:34:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20250724_0001"
down_revision: str | Sequence[str] | None = "c15f023f2624"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create event_outbox table for reliable event publishing."""
    # Create event_outbox table
    op.create_table(
        "event_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("aggregate_id", sa.String(255), nullable=False),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(255), nullable=False),
        sa.Column("event_data", postgresql.JSONB(), nullable=False),
        sa.Column("event_key", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for efficient querying
    op.create_index(
        "idx_outbox_unpublished",
        "event_outbox",
        ["published_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_index("idx_outbox_created", "event_outbox", ["created_at"])
    op.create_index("idx_outbox_aggregate", "event_outbox", ["aggregate_id", "aggregate_type"])


def downgrade() -> None:
    """Drop event_outbox table."""
    # Drop indexes
    op.drop_index("idx_outbox_aggregate", table_name="event_outbox")
    op.drop_index("idx_outbox_created", table_name="event_outbox")
    op.drop_index("idx_outbox_unpublished", table_name="event_outbox")

    # Drop table
    op.drop_table("event_outbox")
