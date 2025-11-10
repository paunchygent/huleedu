"""Add student_prompt_storage_id to assessment_instructions.

Problem: Admin workflow fragmented - admins create instructions/anchors via admin API
but had no pathway to associate student prompts with assignments. Users uploaded prompts
ad-hoc per batch, requiring manual Content Service interaction outside admin workflow.

Solution: Add storage_id reference column (Content Service pointer, not prompt text).
Enables unified admin workflow: all assignment metadata (instructions, anchors, prompts)
managed centrally. Batches with assignment_id auto-lookup prompt via batch_preparation.py.

Phase 4 adds dedicated endpoints: POST/GET /admin/v1/student-prompts + CLI commands.
User ad-hoc batches continue bypassing this table, providing prompt refs directly.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20251110_1200"
down_revision = "20251106_2350"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add student_prompt_storage_id column and index."""
    op.add_column(
        "assessment_instructions",
        sa.Column("student_prompt_storage_id", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_assessment_instructions_student_prompt_storage_id",
        "assessment_instructions",
        ["student_prompt_storage_id"],
    )


def downgrade() -> None:
    """Remove student_prompt_storage_id column and index."""
    op.drop_index(
        "ix_assessment_instructions_student_prompt_storage_id",
        table_name="assessment_instructions",
    )
    op.drop_column("assessment_instructions", "student_prompt_storage_id")
