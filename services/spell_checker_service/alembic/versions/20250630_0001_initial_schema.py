"""Initial spell_checker_service schema.

Revision ID: 20250630_0001
Revises:
Create Date: 2025-06-30 17:58:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20250630_0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Ensure pg_trgm extension for GIN trigram index
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    op.create_table(
        "spellcheck_jobs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("essay_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("language", sa.String(16), nullable=False, server_default="en"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processing_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("batch_id", "essay_id", name="uq_spellcheck_batch_essay"),
    )

    op.create_table(
        "spellcheck_tokens",
        sa.Column("token_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("spellcheck_jobs.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(128), nullable=False),
        sa.Column("suggestions", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("sentence", sa.Text(), nullable=True),
    )

    op.create_index(
        "ix_spellcheck_tokens_token",
        "spellcheck_tokens",
        ["token"],
        postgresql_using="gin",
        postgresql_ops={"token": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_spellcheck_tokens_token", table_name="spellcheck_tokens")
    op.drop_table("spellcheck_tokens")
    op.drop_table("spellcheck_jobs")
