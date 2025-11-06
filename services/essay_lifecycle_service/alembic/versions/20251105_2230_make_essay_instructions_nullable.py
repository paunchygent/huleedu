"""Make essay_instructions nullable for Phase 3.2 prompt architecture

Revision ID: a1f9c8d4e3b2
Revises: 7b4f3c2210d1
Create Date: 2025-11-05 22:30:00.000000

Phase 3.2 replaces essay_instructions with student_prompt_ref stored in batch_metadata.
The essay_instructions field becomes legacy/bridging only during transition period.

This migration makes the column nullable to support the new architecture where
prompts are referenced via Content Service rather than stored inline.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1f9c8d4e3b2"
down_revision: str | Sequence[str] | None = "7b4f3c2210d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make essay_instructions nullable for Phase 3.2 Content Service references."""
    op.alter_column(
        "batch_essay_trackers",
        "essay_instructions",
        existing_type=sa.TEXT(),
        nullable=True,
    )


def downgrade() -> None:
    """Phase 3.2 is a one-way migration per task requirements.

    Reverting would require:
    1. Migrating all student_prompt_ref data back to inline essay_instructions
    2. Ensuring no NULL values exist (data migration required)
    3. Re-applying NOT NULL constraint

    This is architecturally incompatible with Phase 3.2 design.
    """
    raise NotImplementedError(
        "Phase 3.2 is a non-reversible cutover. Downgrade not supported."
    )
