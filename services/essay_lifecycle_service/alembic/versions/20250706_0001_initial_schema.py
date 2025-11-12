"""Initial schema for Essay Lifecycle Service

Revision ID: 20250706_0001
Revises:
Create Date: 2025-07-06 00:01:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20250706_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial schema for Essay Lifecycle Service."""
    # Create essay_status_enum if it does not already exist
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_type
                    WHERE typname = 'essay_status_enum'
                ) THEN
                    CREATE TYPE essay_status_enum AS ENUM (
                        'unregistered',
                        'awaiting_content',
                        'content_provided',
                        'processing',
                        'spellcheck_complete',
                        'nlp_complete',
                        'cj_assessment_complete',
                        'ai_feedback_complete',
                        'completed',
                        'failed'
                    );
                END IF;
            END$$;
            """
        )
    )

    # Create essay_states table
    op.create_table(
        "essay_states",
        sa.Column("essay_id", sa.String(length=255), nullable=False),
        sa.Column("batch_id", sa.String(length=255), nullable=True),
        sa.Column(
            "current_status",
            postgresql.ENUM(name="essay_status_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("processing_metadata", sa.JSON(), nullable=False),
        sa.Column("timeline", sa.JSON(), nullable=False),
        sa.Column("storage_references", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("essay_id"),
    )
    op.create_index(op.f("ix_essay_states_batch_id"), "essay_states", ["batch_id"], unique=False)
    op.create_index(
        op.f("ix_essay_states_current_status"), "essay_states", ["current_status"], unique=False
    )

    # Create batch_essay_trackers table
    op.create_table(
        "batch_essay_trackers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.String(length=255), nullable=False),
        sa.Column("total_slots", sa.Integer(), nullable=False),
        sa.Column("assigned_slots", sa.Integer(), nullable=False),
        sa.Column("batch_metadata", sa.JSON(), nullable=True),
        sa.Column("is_ready", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_batch_essay_trackers_batch_id"), "batch_essay_trackers", ["batch_id"], unique=False
    )

    # Create essay_processing_logs table
    op.create_table(
        "essay_processing_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("essay_id", sa.String(length=255), nullable=False),
        sa.Column("batch_id", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("previous_status", sa.String(length=100), nullable=True),
        sa.Column("new_status", sa.String(length=100), nullable=False),
        sa.Column("event_metadata", sa.JSON(), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["essay_id"], ["essay_states.essay_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_essay_processing_logs_batch_id"),
        "essay_processing_logs",
        ["batch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_essay_processing_logs_correlation_id"),
        "essay_processing_logs",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_essay_processing_logs_essay_id"),
        "essay_processing_logs",
        ["essay_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_essay_processing_logs_event_type"),
        "essay_processing_logs",
        ["event_type"],
        unique=False,
    )


def downgrade() -> None:
    """Drop initial schema for Essay Lifecycle Service."""
    op.drop_index(op.f("ix_essay_processing_logs_event_type"), table_name="essay_processing_logs")
    op.drop_index(op.f("ix_essay_processing_logs_essay_id"), table_name="essay_processing_logs")
    op.drop_index(
        op.f("ix_essay_processing_logs_correlation_id"), table_name="essay_processing_logs"
    )
    op.drop_index(op.f("ix_essay_processing_logs_batch_id"), table_name="essay_processing_logs")
    op.drop_table("essay_processing_logs")

    op.drop_index(op.f("ix_batch_essay_trackers_batch_id"), table_name="batch_essay_trackers")
    op.drop_table("batch_essay_trackers")

    op.drop_index(op.f("ix_essay_states_current_status"), table_name="essay_states")
    op.drop_index(op.f("ix_essay_states_batch_id"), table_name="essay_states")
    op.drop_table("essay_states")

    op.execute(sa.text("DROP TYPE IF EXISTS essay_status_enum"))
