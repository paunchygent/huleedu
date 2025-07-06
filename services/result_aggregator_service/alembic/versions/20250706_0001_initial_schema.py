"""Initial schema for Result Aggregator Service

Revision ID: 20250706_0001
Revises:
Create Date: 2025-07-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20250706_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial schema for Result Aggregator Service."""
    # Create BatchStatus enum
    batch_status_enum = postgresql.ENUM(
        "AWAITING_CONTENT_VALIDATION",
        "CONTENT_VALIDATION_FAILED",
        "CONTENT_VALIDATED",
        "PROCESSING",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        name="batchstatus",
    )
    batch_status_enum.create(op.get_bind())

    # Create ProcessingStage enum
    processing_stage_enum = postgresql.ENUM(
        "PENDING",
        "IN_PROGRESS",
        "COMPLETED",
        "FAILED",
        "SKIPPED",
        name="processingstage",
    )
    processing_stage_enum.create(op.get_bind())

    # Create batch_results table
    op.create_table(
        "batch_results",
        sa.Column("batch_id", sa.String(255), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column(
            "overall_status",
            sa.Enum(
                "AWAITING_CONTENT_VALIDATION",
                "CONTENT_VALIDATION_FAILED",
                "CONTENT_VALIDATED",
                "PROCESSING",
                "COMPLETED",
                "FAILED",
                "CANCELLED",
                name="batchstatus",
            ),
            nullable=False,
        ),
        sa.Column("essay_count", sa.Integer(), nullable=False),
        sa.Column("completed_essay_count", sa.Integer(), nullable=False),
        sa.Column("failed_essay_count", sa.Integer(), nullable=False),
        sa.Column("requested_pipeline", sa.String(100), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(), nullable=True),
        sa.Column("processing_completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("batch_id"),
    )

    # Create indexes for batch_results
    op.create_index("idx_user_batch", "batch_results", ["user_id", "batch_id"])
    op.create_index("idx_batch_status", "batch_results", ["overall_status"])
    op.create_index("idx_batch_created", "batch_results", ["created_at"])
    op.create_index(op.f("ix_batch_results_user_id"), "batch_results", ["user_id"], unique=False)

    # Create essay_results table
    op.create_table(
        "essay_results",
        sa.Column("essay_id", sa.String(255), nullable=False),
        sa.Column("batch_id", sa.String(255), nullable=False),
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column("original_text_storage_id", sa.String(255), nullable=True),
        sa.Column(
            "spellcheck_status",
            sa.Enum(
                "PENDING",
                "IN_PROGRESS",
                "COMPLETED",
                "FAILED",
                "SKIPPED",
                name="processingstage",
            ),
            nullable=True,
        ),
        sa.Column("spellcheck_correction_count", sa.Integer(), nullable=True),
        sa.Column("spellcheck_corrected_text_storage_id", sa.String(255), nullable=True),
        sa.Column("spellcheck_completed_at", sa.DateTime(), nullable=True),
        sa.Column("spellcheck_error", sa.String(500), nullable=True),
        sa.Column(
            "cj_assessment_status",
            sa.Enum(
                "PENDING",
                "IN_PROGRESS",
                "COMPLETED",
                "FAILED",
                "SKIPPED",
                name="processingstage",
            ),
            nullable=True,
        ),
        sa.Column("cj_rank", sa.Integer(), nullable=True),
        sa.Column("cj_score", sa.Float(), nullable=True),
        sa.Column("cj_comparison_count", sa.Integer(), nullable=True),
        sa.Column("cj_assessment_completed_at", sa.DateTime(), nullable=True),
        sa.Column("cj_assessment_error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["batch_id"], ["batch_results.batch_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("essay_id"),
    )

    # Create indexes for essay_results
    op.create_index("idx_essay_batch", "essay_results", ["batch_id", "essay_id"])
    op.create_index("idx_essay_spellcheck_status", "essay_results", ["spellcheck_status"])
    op.create_index("idx_essay_cj_status", "essay_results", ["cj_assessment_status"])
    op.create_index(op.f("ix_essay_results_batch_id"), "essay_results", ["batch_id"], unique=False)

    # Create unique constraint
    op.create_unique_constraint("uq_batch_essay", "essay_results", ["batch_id", "essay_id"])


def downgrade() -> None:
    """Drop all tables and enums."""
    # Drop tables in reverse order
    op.drop_table("essay_results")
    op.drop_table("batch_results")

    # Drop enums
    processing_stage_enum = postgresql.ENUM(
        "PENDING",
        "IN_PROGRESS",
        "COMPLETED",
        "FAILED",
        "SKIPPED",
        name="processingstage",
    )
    processing_stage_enum.drop(op.get_bind())

    batch_status_enum = postgresql.ENUM(
        "AWAITING_CONTENT_VALIDATION",
        "CONTENT_VALIDATION_FAILED",
        "CONTENT_VALIDATED",
        "PROCESSING",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        name="batchstatus",
    )
    batch_status_enum.drop(op.get_bind())
