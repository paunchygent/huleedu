"""Add security and session management fields

Revision ID: 5c38467d2203
Revises: adc8538fe76d
Create Date: 2025-08-21 13:16:30.332276

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "5c38467d2203"
down_revision: Union[str, None] = "adc8538fe76d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the migration."""
    # Add security fields to users table
    op.add_column("users", sa.Column("failed_login_attempts", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_failed_login_at", sa.DateTime(timezone=True), nullable=True))
    
    # Create audit_logs table for security auditing
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),  # IPv6 support
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("idx_audit_logs_action", "audit_logs", ["action"])
    op.create_index("idx_audit_logs_created_at", "audit_logs", ["created_at"])
    
    # Create user_sessions table for enhanced session management
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("jti", sa.String(length=255), nullable=False),
        sa.Column("device_name", sa.String(length=255), nullable=True),
        sa.Column("device_type", sa.String(length=50), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("last_activity", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jti"),
    )
    op.create_index("idx_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("idx_user_sessions_jti", "user_sessions", ["jti"])
    op.create_index("idx_user_sessions_expires_at", "user_sessions", ["expires_at"])


def downgrade() -> None:
    """Revert the migration."""
    # Drop user_sessions table
    op.drop_index("idx_user_sessions_expires_at", "user_sessions")
    op.drop_index("idx_user_sessions_jti", "user_sessions")
    op.drop_index("idx_user_sessions_user_id", "user_sessions")
    op.drop_table("user_sessions")
    
    # Drop audit_logs table
    op.drop_index("idx_audit_logs_created_at", "audit_logs")
    op.drop_index("idx_audit_logs_action", "audit_logs")
    op.drop_index("idx_audit_logs_user_id", "audit_logs")
    op.drop_table("audit_logs")
    
    # Remove security fields from users table
    op.drop_column("users", "last_failed_login_at")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
