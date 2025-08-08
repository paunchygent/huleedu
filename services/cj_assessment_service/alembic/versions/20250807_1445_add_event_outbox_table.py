"""Add event outbox table for transactional event publishing

Revision ID: add_event_outbox_table
Revises: d3f4e5f6a7b8
Create Date: 2025-08-07 14:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_event_outbox_table'
down_revision = 'd03b409524ae'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create event_outbox table for transactional outbox pattern."""
    op.create_table(
        'event_outbox',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('aggregate_id', sa.String(255), nullable=False),
        sa.Column('aggregate_type', sa.String(100), nullable=False),
        sa.Column('event_type', sa.String(255), nullable=False),
        sa.Column('event_data', postgresql.JSON(astext_type=sa.Text()),
                  nullable=False),
        sa.Column('event_key', sa.String(255), nullable=True),
        sa.Column('topic', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('retry_count', sa.Integer(), server_default=sa.text('0'),
                  nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Critical indexes for outbox processing
    op.create_index('ix_event_outbox_unpublished', 'event_outbox',
                    ['published_at', 'created_at'],
                    postgresql_where=sa.text('published_at IS NULL'))
    op.create_index('ix_event_outbox_aggregate', 'event_outbox',
                    ['aggregate_type', 'aggregate_id'])
    op.create_index('ix_event_outbox_event_type', 'event_outbox',
                    ['event_type'])


def downgrade() -> None:
    """Drop event_outbox table and indexes."""
    op.drop_index('ix_event_outbox_event_type', table_name='event_outbox')
    op.drop_index('ix_event_outbox_aggregate', table_name='event_outbox')
    op.drop_index('ix_event_outbox_unpublished', table_name='event_outbox')
    op.drop_table('event_outbox')