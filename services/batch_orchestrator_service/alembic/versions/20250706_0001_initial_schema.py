"""Initial schema for Batch Orchestrator Service

Revision ID: 20250706_0001
Revises:
Create Date: 2025-07-06 00:01:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20250706_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial schema for Batch Orchestrator Service."""
    # Create batch_status_enum
    op.execute(
        sa.text(
            """
            CREATE TYPE batch_status_enum AS ENUM (
                'awaiting_content_validation',
                'processing',
                'completed',
                'failed',
                'cancelled'
            )
            """
        )
    )

    # Create pipeline_phase_enum
    op.execute(
        sa.text(
            """
            CREATE TYPE pipeline_phase_enum AS ENUM (
                'spellcheck',
                'nlp_analysis',
                'cj_assessment',
                'ai_feedback'
            )
            """
        )
    )

    # Create phase_status_enum
    op.execute(
        sa.text(
            """
            CREATE TYPE phase_status_enum AS ENUM (
                'pending',
                'initiated',
                'in_progress',
                'completed',
                'failed',
                'cancelled'
            )
            """
        )
    )

    # Create batches table
    op.create_table(
        "batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="batch_status_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("requested_pipelines", sa.JSON(), nullable=True),
        sa.Column("pipeline_configuration", sa.JSON(), nullable=True),
        sa.Column("total_essays", sa.Integer(), nullable=True),
        sa.Column("processed_essays", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("processing_metadata", sa.JSON(), nullable=True),
        sa.Column("error_details", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_batches_correlation_id"), "batches", ["correlation_id"], unique=False)
    op.create_index(op.f("ix_batches_status"), "batches", ["status"], unique=False)

    # Create phase_status_log table
    op.create_table(
        "phase_status_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column(
            "phase",
            postgresql.ENUM(name="pipeline_phase_enum", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name="phase_status_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("phase_started_at", sa.DateTime(), nullable=True),
        sa.Column("phase_completed_at", sa.DateTime(), nullable=True),
        sa.Column("essays_processed", sa.Integer(), nullable=False),
        sa.Column("essays_failed", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", sa.JSON(), nullable=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("processing_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_phase_status_log_batch_id"), "phase_status_log", ["batch_id"], unique=False
    )
    op.create_index(op.f("ix_phase_status_log_phase"), "phase_status_log", ["phase"], unique=False)
    op.create_index(
        op.f("ix_phase_status_log_status"), "phase_status_log", ["status"], unique=False
    )

    # Create configuration_snapshots table
    op.create_table(
        "configuration_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("snapshot_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("pipeline_definition", sa.JSON(), nullable=False),
        sa.Column("configuration_version", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("validation_status", sa.String(length=50), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("source_system", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("additional_metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_configuration_snapshots_batch_id"),
        "configuration_snapshots",
        ["batch_id"],
        unique=False,
    )

    # Create batch_essays table
    op.create_table(
        "batch_essays",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("essay_id", sa.String(length=36), nullable=False),
        sa.Column("content_reference", sa.JSON(), nullable=False),
        sa.Column("student_metadata", sa.JSON(), nullable=True),
        sa.Column("processing_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_batch_essays_batch_id"), "batch_essays", ["batch_id"], unique=False)
    op.create_index(op.f("ix_batch_essays_essay_id"), "batch_essays", ["essay_id"], unique=False)


def downgrade() -> None:
    """Drop initial schema for Batch Orchestrator Service."""
    op.drop_index(op.f("ix_batch_essays_essay_id"), table_name="batch_essays")
    op.drop_index(op.f("ix_batch_essays_batch_id"), table_name="batch_essays")
    op.drop_table("batch_essays")

    op.drop_index(op.f("ix_configuration_snapshots_batch_id"), table_name="configuration_snapshots")
    op.drop_table("configuration_snapshots")

    op.drop_index(op.f("ix_phase_status_log_status"), table_name="phase_status_log")
    op.drop_index(op.f("ix_phase_status_log_phase"), table_name="phase_status_log")
    op.drop_index(op.f("ix_phase_status_log_batch_id"), table_name="phase_status_log")
    op.drop_table("phase_status_log")

    op.drop_index(op.f("ix_batches_status"), table_name="batches")
    op.drop_index(op.f("ix_batches_correlation_id"), table_name="batches")
    op.drop_table("batches")

    op.execute(sa.text("DROP TYPE IF EXISTS phase_status_enum"))
    op.execute(sa.text("DROP TYPE IF EXISTS pipeline_phase_enum"))
    op.execute(sa.text("DROP TYPE IF EXISTS batch_status_enum"))
