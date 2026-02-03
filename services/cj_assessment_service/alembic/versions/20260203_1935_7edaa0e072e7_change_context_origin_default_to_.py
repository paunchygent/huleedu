"""change_context_origin_default_to_research_experiment

Revision ID: 7edaa0e072e7
Revises: 20260203_1200
Create Date: 2026-02-03 19:35:56.485227

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7edaa0e072e7"
down_revision: Union[str, Sequence[str], None] = "20260203_1200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Canonical assignments are only created after prompt/rubric iteration and
    explicit sign-off. Defaulting to canonical would invert the workflow.
    """
    op.alter_column(
        "assessment_instructions",
        "context_origin",
        existing_type=sa.String(64),
        server_default="research_experiment",
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "assessment_instructions",
        "context_origin",
        existing_type=sa.String(64),
        server_default="canonical_national",
        existing_nullable=False,
    )
