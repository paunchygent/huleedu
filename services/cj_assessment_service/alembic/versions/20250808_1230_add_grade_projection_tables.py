"""Add grade projection and assessment context tables

Revision ID: add_grade_projection_tables
Revises: add_event_outbox_table
Create Date: 2025-08-08 12:30:00.000000

This migration adds support for grade projection functionality:
- AssessmentInstruction: Store instructions for AI judges
- AnchorEssayReference: Reference anchor essays for calibration
- GradeProjection: Store predicted grades with confidence scores
- Updates CJBatchUpload with assignment_id field
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_grade_projection_tables"
down_revision: Union[str, None] = "add_event_outbox_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create grade projection related tables and update existing tables."""

    # Create assessment_instructions table
    op.create_table(
        "assessment_instructions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assignment_id", sa.String(100), nullable=True),
        sa.Column("course_id", sa.String(50), nullable=True),
        sa.Column("instructions_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assignment_id"),
        sa.CheckConstraint(
            "(assignment_id IS NOT NULL AND course_id IS NULL) OR "
            "(assignment_id IS NULL AND course_id IS NOT NULL)",
            name="chk_context_type",
        ),
        comment="Stores assessment instructions for AI judges, linked to assignment or course",
    )
    op.create_index(
        op.f("ix_assessment_instructions_assignment_id"),
        "assessment_instructions",
        ["assignment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assessment_instructions_course_id"),
        "assessment_instructions",
        ["course_id"],
        unique=False,
    )

    # Create anchor_essay_references table
    op.create_table(
        "anchor_essay_references",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("grade", sa.String(3), nullable=False),
        sa.Column("content_id", sa.String(255), nullable=False),
        sa.Column("assignment_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="References to pre-graded anchor essays stored in Content Service",
    )
    op.create_index(
        op.f("ix_anchor_essay_references_grade"),
        "anchor_essay_references",
        ["grade"],
        unique=False,
    )
    op.create_index(
        op.f("ix_anchor_essay_references_assignment_id"),
        "anchor_essay_references",
        ["assignment_id"],
        unique=False,
    )

    # Create grade_projections table
    op.create_table(
        "grade_projections",
        sa.Column("els_essay_id", sa.String(255), nullable=False),
        sa.Column("cj_batch_id", sa.Integer(), nullable=False),
        sa.Column("primary_grade", sa.String(3), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("confidence_label", sa.String(10), nullable=False),
        sa.Column("calculation_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["els_essay_id"],
            ["cj_processed_essays.els_essay_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cj_batch_id"],
            ["cj_batch_uploads.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("els_essay_id", "cj_batch_id"),
        comment="Stores grade projections with confidence scores for assessed essays",
    )
    op.create_index(
        "idx_batch_grade",
        "grade_projections",
        ["cj_batch_id", "primary_grade"],
        unique=False,
    )

    # Add assignment_id column to cj_batch_uploads
    op.add_column(
        "cj_batch_uploads",
        sa.Column(
            "assignment_id",
            sa.String(100),
            nullable=True,
            comment="Optional assignment context for grade projection",
        ),
    )


def downgrade() -> None:
    """Drop grade projection related tables and columns."""

    # Remove assignment_id from cj_batch_uploads
    op.drop_column("cj_batch_uploads", "assignment_id")

    # Drop grade_projections table
    op.drop_index("idx_batch_grade", table_name="grade_projections")
    op.drop_table("grade_projections")

    # Drop anchor_essay_references table
    op.drop_index(
        op.f("ix_anchor_essay_references_assignment_id"),
        table_name="anchor_essay_references",
    )
    op.drop_index(
        op.f("ix_anchor_essay_references_grade"),
        table_name="anchor_essay_references",
    )
    op.drop_table("anchor_essay_references")

    # Drop assessment_instructions table
    op.drop_index(
        op.f("ix_assessment_instructions_course_id"),
        table_name="assessment_instructions",
    )
    op.drop_index(
        op.f("ix_assessment_instructions_assignment_id"),
        table_name="assessment_instructions",
    )
    op.drop_table("assessment_instructions")
