"""add_pair_generation_mode_to_comparison_pair

Revision ID: 2ea57f0f8b9d
Revises: 20251121_1800
Create Date: 2025-12-07 01:36:02.502988

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2ea57f0f8b9d"
down_revision: Union[str, Sequence[str], None] = "20251121_1800"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "cj_comparison_pairs",
        sa.Column("pair_generation_mode", sa.String(length=20), nullable=True),
    )
    op.create_index(
        op.f("ix_cj_comparison_pairs_pair_generation_mode"),
        "cj_comparison_pairs",
        ["pair_generation_mode"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_cj_comparison_pairs_pair_generation_mode"), table_name="cj_comparison_pairs"
    )
    op.drop_column("cj_comparison_pairs", "pair_generation_mode")
