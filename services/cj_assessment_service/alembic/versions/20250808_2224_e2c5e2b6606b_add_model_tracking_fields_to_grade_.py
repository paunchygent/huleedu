"""Add model tracking fields to grade_projections

Revision ID: e2c5e2b6606b
Revises: 2ff2ff0e481c
Create Date: 2025-08-08 22:24:01.935329

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e2c5e2b6606b"
down_revision: Union[str, Sequence[str], None] = "2ff2ff0e481c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('grade_projections', 
        sa.Column('assessment_method', sa.String(50), nullable=False, server_default='cj_assessment'))
    op.add_column('grade_projections', 
        sa.Column('model_used', sa.String(100), nullable=True))
    op.add_column('grade_projections', 
        sa.Column('model_provider', sa.String(50), nullable=True))
    op.add_column('grade_projections', 
        sa.Column('normalized_score', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('grade_projections', 'normalized_score')
    op.drop_column('grade_projections', 'model_provider')
    op.drop_column('grade_projections', 'model_used')
    op.drop_column('grade_projections', 'assessment_method')
