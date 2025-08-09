"""Rename content_id to text_storage_id in anchor_essay_references

Revision ID: 2ff2ff0e481c
Revises: add_grade_projection_tables
Create Date: 2025-08-08 22:22:59.033675

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2ff2ff0e481c"
down_revision: Union[str, Sequence[str], None] = "add_grade_projection_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("anchor_essay_references", "content_id", new_column_name="text_storage_id")


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column("anchor_essay_references", "text_storage_id", new_column_name="content_id")
