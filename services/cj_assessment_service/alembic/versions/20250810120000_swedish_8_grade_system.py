"""Migrate to Swedish 8-grade system

Revision ID: 20250810120000
Revises: 20250810_1530_support_fine_grained_grades
Create Date: 2025-08-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250810120000'
down_revision = '20250810_1530_support_fine_grained_grades'
branch_labels = None
depends_on = None


def upgrade():
    # Add column for population prior (for future flexibility)
    op.add_column('grade_projections',
        sa.Column('population_prior', sa.Float(), nullable=True)
    )
    
    # Update any existing projections metadata
    op.execute("""
        UPDATE grade_projections 
        SET calculation_metadata = jsonb_set(
            calculation_metadata,
            '{grade_system}',
            '"swedish_8_grade"'
        )
        WHERE calculation_metadata IS NOT NULL
    """)


def downgrade():
    op.drop_column('grade_projections', 'population_prior')
    # Downgrade does not remove the grade_system from metadata, as it's not easy to know what to revert to.
    # The application logic should be able to handle the old system if the code is reverted.

