"""Add batch state management tables

Revision ID: d3f4e5f6a7b8
Revises: af94ec26dba0
Create Date: 2025-01-15 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "d3f4e5f6a7b8"
down_revision = "af94ec26dba0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create batch state enum
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_type
                    WHERE typname = 'cj_batch_state_enum'
                ) THEN
                    CREATE TYPE cj_batch_state_enum AS ENUM (
                        'INITIALIZING',
                        'GENERATING_PAIRS',
                        'WAITING_CALLBACKS',
                        'SCORING',
                        'COMPLETED',
                        'FAILED',
                        'CANCELLED'
                    );
                END IF;
            END$$;
            """
        )
    )

    # Create batch states table
    op.create_table(
        "cj_batch_states",
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column(
            "state",
            postgresql.ENUM(
                name="cj_batch_state_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("total_comparisons", sa.Integer(), nullable=False),
        sa.Column("submitted_comparisons", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_comparisons", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_comparisons", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "partial_scoring_triggered", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("completion_threshold_pct", sa.Integer(), nullable=False, server_default="95"),
        sa.Column("current_iteration", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("processing_metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["cj_batch_uploads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("batch_id"),
    )
    op.create_index(op.f("ix_cj_batch_states_state"), "cj_batch_states", ["state"], unique=False)

    # Add correlation tracking to comparison pairs
    op.add_column(
        "cj_comparison_pairs",
        sa.Column("request_correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "cj_comparison_pairs", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "cj_comparison_pairs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        op.f("ix_cj_comparison_pairs_request_correlation_id"),
        "cj_comparison_pairs",
        ["request_correlation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_cj_comparison_pairs_request_correlation_id"), table_name="cj_comparison_pairs"
    )
    op.drop_column("cj_comparison_pairs", "completed_at")
    op.drop_column("cj_comparison_pairs", "submitted_at")
    op.drop_column("cj_comparison_pairs", "request_correlation_id")
    op.drop_index(op.f("ix_cj_batch_states_state"), table_name="cj_batch_states")
    op.drop_table("cj_batch_states")
    op.execute(sa.text("DROP TYPE IF EXISTS cj_batch_state_enum"))
