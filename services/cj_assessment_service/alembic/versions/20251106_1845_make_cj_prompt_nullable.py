"""Make essay_instructions nullable for CJ batches."""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20251106_1845"
down_revision = "20251103_2305_add_grade_scale_to_instructions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "cj_batch_uploads",
        "essay_instructions",
        existing_type=sa.Text(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "cj_batch_uploads",
        "essay_instructions",
        existing_type=sa.Text(),
        nullable=False,
    )
