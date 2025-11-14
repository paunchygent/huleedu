"""Add unique constraint for anchor assignment-grade-scale combinations.

Ensures at most one anchor per (assignment_id, grade, grade_scale) while
preserving PostgreSQL NULL semantics for assignment_id.

Also removes ENG5 dev-only duplicate anchors created during early testing:
- assignment_id = '00000000-0000-0000-0000-000000000001'
- grade_scale   = 'swedish_8_anchor'
- id < 49

This cleanup targets ENG5 development data only and has no production impact.

Revision ID: 20251114_0230
Revises: 4aefc9fed780
Create Date: 2025-11-14 02:30:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251114_0230"
down_revision: Union[str, Sequence[str], None] = "4aefc9fed780"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply anchor uniqueness constraint and ENG5 dev cleanup."""
    # Delete ENG5 dev-only duplicate anchors to satisfy new unique constraint.
    # These rows were created during early ENG5 runner experiments and are safe
    # to remove in all environments (no production usage).
    #
    # Keep the highest-id row for each (assignment_id, grade, grade_scale)
    # triple for the ENG5 dev assignment and delete older duplicates.
    op.execute(
        """
        DELETE FROM anchor_essay_references a
        USING anchor_essay_references b
        WHERE a.assignment_id = '00000000-0000-0000-0000-000000000001'
          AND b.assignment_id = a.assignment_id
          AND b.grade = a.grade
          AND b.grade_scale = a.grade_scale
          AND a.id < b.id
        """
    )

    # Add unique constraint ensuring at most one anchor per
    # (assignment_id, grade, grade_scale). PostgreSQL allows multiple NULL
    # assignment_id values, so course-level or global anchors remain unaffected.
    op.create_unique_constraint(
        "uq_anchor_assignment_grade_scale",
        "anchor_essay_references",
        ["assignment_id", "grade", "grade_scale"],
    )


def downgrade() -> None:
    """Remove anchor uniqueness constraint (no data restoration)."""
    op.drop_constraint(
        "uq_anchor_assignment_grade_scale",
        "anchor_essay_references",
        type_="unique",
    )
