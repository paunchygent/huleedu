"""Drop essay_instructions column from CJ batch uploads."""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251106_2350"
down_revision = "20251106_1845"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("cj_batch_uploads", "essay_instructions")


def downgrade() -> None:
    op.add_column(
        "cj_batch_uploads",
        sa.Column("essay_instructions", sa.Text(), nullable=True),
    )
