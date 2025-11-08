"""Remove legacy essay_instructions column after prompt reference migration

Revision ID: c2d4e6f7a8b9
Revises: a1f9c8d4e3b2
Create Date: 2025-11-06 21:05:00.000000

This migration drops the deprecated essay_instructions column from
batch_essay_trackers now that prompt references are persisted exclusively via
student_prompt_ref metadata.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2d4e6f7a8b9"
down_revision: str | Sequence[str] | None = "a1f9c8d4e3b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop essay_instructions column; prompt metadata lives in batch_metadata."""
    with op.batch_alter_table("batch_essay_trackers") as batch_op:
        batch_op.drop_column("essay_instructions")


def downgrade() -> None:
    """Reintroducing essay_instructions would require data backfill; unsupported."""
    raise NotImplementedError(
        "essay_instructions column removal is irreversible under Phase 3.2 design"
    )
