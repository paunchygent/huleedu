"""Add email verification tokens table for user email verification workflow."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b467d39e123b"
down_revision = "20240818_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # email_verification_tokens table
    op.create_table(
        "email_verification_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes for performance and constraints
    op.create_index(
        "ix_email_verification_tokens_user_id",
        "email_verification_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_email_verification_tokens_token", "email_verification_tokens", ["token"], unique=True
    )
    op.create_index(
        "ix_email_verification_tokens_expires",
        "email_verification_tokens",
        ["expires_at"],
        unique=False,
    )

    # Foreign key constraint
    op.create_foreign_key(
        "fk_email_verification_tokens_user_id",
        "email_verification_tokens",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_email_verification_tokens_user_id", "email_verification_tokens", type_="foreignkey"
    )
    op.drop_index("ix_email_verification_tokens_expires", table_name="email_verification_tokens")
    op.drop_index("ix_email_verification_tokens_token", table_name="email_verification_tokens")
    op.drop_index("ix_email_verification_tokens_user_id", table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")
