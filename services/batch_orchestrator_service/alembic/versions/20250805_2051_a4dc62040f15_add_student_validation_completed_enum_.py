"""Add student_validation_completed enum value

Revision ID: a4dc62040f15
Revises: add_class_id_to_batches
Create Date: 2025-08-05 20:51:59.415901

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4dc62040f15"
down_revision: Union[str, None] = "add_class_id_to_batches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the new enum value to batch_status_enum
    op.execute(
        "ALTER TYPE batch_status_enum ADD VALUE IF NOT EXISTS "
        "'student_validation_completed' AFTER 'awaiting_student_validation'"
    )


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values
    # This is a no-op but we document the limitation
    pass
