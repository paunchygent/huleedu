"""Add context_origin to assessment_instructions.

This flag documents and enforces ownership semantics for assignment-scoped
assessment configuration, primarily used to distinguish canonical/national
assignments from teacher-owned/ad-hoc configurations.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260203_1200"
down_revision = "cj_forced_recovery_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add context_origin column and index."""
    op.add_column(
        "assessment_instructions",
        sa.Column(
            "context_origin",
            sa.String(64),
            nullable=False,
            server_default="canonical_national",
        ),
    )

    # Backfill: the existing ENG5 NP experiment assignment is not canonical.
    # It is used for rubric/system-prompt tuning and must allow request-time overrides.
    op.execute(
        """
        UPDATE assessment_instructions
        SET context_origin = 'research_experiment'
        WHERE assignment_id = '00000000-0000-0000-0000-000000000001'
        """
    )

    op.create_index(
        "ix_assessment_instructions_context_origin",
        "assessment_instructions",
        ["context_origin"],
    )


def downgrade() -> None:
    """Remove context_origin column and index."""
    op.drop_index(
        "ix_assessment_instructions_context_origin",
        table_name="assessment_instructions",
    )
    op.drop_column("assessment_instructions", "context_origin")
