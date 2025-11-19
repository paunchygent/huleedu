"""Add total_budget column and reset iteration defaults.

Ensures CJ batch state tracking preserves the original comparison budget and
starts iteration counters at zero for accurate multi-iteration accounting.

Revision ID: 20251119_1200
Revises: 20251114_0900
Create Date: 2025-11-19 12:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251119_1200"
down_revision: Union[str, Sequence[str], None] = "20251114_0900"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add total_budget column and normalize iteration defaults."""

    op.add_column("cj_batch_states", sa.Column("total_budget", sa.Integer(), nullable=True))

    # Initialize the new column using historical total comparisons so legacy rows
    # retain their requested budgets.
    op.execute(
        """
        UPDATE cj_batch_states
        SET total_budget = total_comparisons
        WHERE total_budget IS NULL
        """
    )

    # Ensure new rows start at iteration 0 for more predictable comparisons.
    op.alter_column(
        "cj_batch_states",
        "current_iteration",
        existing_type=sa.Integer(),
        server_default=sa.text("0"),
    )


def downgrade() -> None:
    """Remove total_budget column and restore original defaults."""

    op.alter_column(
        "cj_batch_states",
        "current_iteration",
        existing_type=sa.Integer(),
        server_default=sa.text("1"),
    )
    op.drop_column("cj_batch_states", "total_budget")
