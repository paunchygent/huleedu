"""Initial schema for CJ Assessment Service

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
    """Create initial schema for CJ Assessment Service."""
    # Create CJ batch status enum
    cj_batch_status_enum = postgresql.ENUM(
        "PENDING",
        "FETCHING_CONTENT",
        "PERFORMING_COMPARISONS",
        "COMPLETE_STABLE",
        "COMPLETE_MAX_COMPARISONS",
        "ERROR_PROCESSING",
        "ERROR_ESSAY_PROCESSING",
        name="cj_batch_status_enum",
    )
    cj_batch_status_enum.create(op.get_bind())

    # Create cj_batch_uploads table
    op.create_table(
        "cj_batch_uploads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bos_batch_id", sa.String(36), nullable=False),
        sa.Column("event_correlation_id", sa.String(36), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("course_code", sa.String(50), nullable=False),
        sa.Column("essay_instructions", sa.Text(), nullable=False),
        sa.Column("expected_essay_count", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "FETCHING_CONTENT",
                "PERFORMING_COMPARISONS",
                "COMPLETE_STABLE",
                "COMPLETE_MAX_COMPARISONS",
                "ERROR_PROCESSING",
                "ERROR_ESSAY_PROCESSING",
                name="cj_batch_status_enum",
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("processing_metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for cj_batch_uploads
    op.create_index(
        op.f("ix_cj_batch_uploads_bos_batch_id"),
        "cj_batch_uploads",
        ["bos_batch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cj_batch_uploads_status"),
        "cj_batch_uploads",
        ["status"],
        unique=False,
    )

    # Create cj_processed_essays table
    op.create_table(
        "cj_processed_essays",
        sa.Column("els_essay_id", sa.String(36), nullable=False),
        sa.Column("cj_batch_id", sa.Integer(), nullable=False),
        sa.Column("text_storage_id", sa.String(256), nullable=False),
        sa.Column("assessment_input_text", sa.Text(), nullable=False),
        sa.Column("current_bt_score", sa.Float(), nullable=True),
        sa.Column("comparison_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("processing_metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["cj_batch_id"], ["cj_batch_uploads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("els_essay_id"),
    )

    # Create indexes for cj_processed_essays
    op.create_index(
        op.f("ix_cj_processed_essays_cj_batch_id"),
        "cj_processed_essays",
        ["cj_batch_id"],
        unique=False,
    )

    # Create cj_comparison_pairs table
    op.create_table(
        "cj_comparison_pairs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cj_batch_id", sa.Integer(), nullable=False),
        sa.Column("essay_a_els_id", sa.String(36), nullable=False),
        sa.Column("essay_b_els_id", sa.String(36), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("winner", sa.String(20), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("raw_llm_response", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("processing_metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["cj_batch_id"], ["cj_batch_uploads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["essay_a_els_id"], ["cj_processed_essays.els_essay_id"]),
        sa.ForeignKeyConstraint(["essay_b_els_id"], ["cj_processed_essays.els_essay_id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for cj_comparison_pairs
    op.create_index(
        op.f("ix_cj_comparison_pairs_cj_batch_id"),
        "cj_comparison_pairs",
        ["cj_batch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cj_comparison_pairs_essay_a_els_id"),
        "cj_comparison_pairs",
        ["essay_a_els_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cj_comparison_pairs_essay_b_els_id"),
        "cj_comparison_pairs",
        ["essay_b_els_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop all tables and enums."""
    # Drop tables in reverse order
    op.drop_table("cj_comparison_pairs")
    op.drop_table("cj_processed_essays")
    op.drop_table("cj_batch_uploads")

    # Drop enum
    cj_batch_status_enum = postgresql.ENUM(
        "PENDING",
        "FETCHING_CONTENT",
        "PERFORMING_COMPARISONS",
        "COMPLETE_STABLE",
        "COMPLETE_MAX_COMPARISONS",
        "ERROR_PROCESSING",
        "ERROR_ESSAY_PROCESSING",
        name="cj_batch_status_enum",
    )
    cj_batch_status_enum.drop(op.get_bind())
