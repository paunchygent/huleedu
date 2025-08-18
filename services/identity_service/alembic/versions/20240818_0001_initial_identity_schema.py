"""Initial Identity Service schema: users, refresh_sessions, event_outbox.

Revision ID: 20240818_0001
Revises: 
Create Date: 2024-08-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20240818_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("org_id", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_org_id", "users", ["org_id"], unique=False)

    # refresh_sessions table
    op.create_table(
        "refresh_sessions",
        sa.Column("jti", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exp_ts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"], unique=False)

    # event_outbox table
    op.create_table(
        "event_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("aggregate_id", sa.String(length=255), nullable=False),
        sa.Column("aggregate_type", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("event_data", sa.JSON(), nullable=False),
        sa.Column("event_key", sa.String(length=255), nullable=True),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    # Indexes for event_outbox
    op.create_index("ix_event_outbox_aggregate", "event_outbox", ["aggregate_type", "aggregate_id"], unique=False)
    op.create_index("ix_event_outbox_event_type", "event_outbox", ["event_type"], unique=False)
    op.create_index("ix_event_outbox_topic", "event_outbox", ["topic"], unique=False)
    # Partial index for unpublished events (PostgreSQL)
    op.execute(
        "CREATE INDEX ix_event_outbox_unpublished_topic ON event_outbox (published_at, topic, created_at) WHERE published_at IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_event_outbox_unpublished_topic", table_name="event_outbox")
    op.drop_index("ix_event_outbox_topic", table_name="event_outbox")
    op.drop_index("ix_event_outbox_event_type", table_name="event_outbox")
    op.drop_index("ix_event_outbox_aggregate", table_name="event_outbox")
    op.drop_table("event_outbox")
    op.drop_index("ix_refresh_sessions_user_id", table_name="refresh_sessions")
    op.drop_table("refresh_sessions")
    op.drop_index("ix_users_org_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

