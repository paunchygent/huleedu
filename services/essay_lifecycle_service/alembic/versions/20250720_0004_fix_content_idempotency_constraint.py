"""Fix content idempotency constraint to handle NULL text_storage_id

Revision ID: 20250720_0004
Revises: 20250719_0003
Create Date: 2025-07-20 12:00:00.000000

This migration fixes the content idempotency constraint to allow multiple
essays with NULL text_storage_id in the same batch, while still preventing
duplicate content assignments when text_storage_id is not NULL.

The issue: The current unique constraint (batch_id, text_storage_id) was
preventing multiple essays from being created in the same batch when they
all start with text_storage_id = NULL.

The fix: Replace the unique constraint with a partial unique index that
only applies when text_storage_id IS NOT NULL.
"""


from alembic import op

# revision identifiers, used by Alembic.
revision = "20250720_0004"
down_revision = "20250719_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Fix content idempotency constraint to handle NULL text_storage_id."""

    # Step 1: Drop the existing unique constraint that was too restrictive
    op.drop_constraint("uq_essay_content_idempotency", "essay_states", type_="unique")

    # Step 2: Create a partial unique index that only applies when text_storage_id IS NOT NULL
    # This allows multiple essays with NULL text_storage_id in the same batch
    # but prevents duplicate content assignments when text_storage_id is assigned
    op.execute("""
        CREATE UNIQUE INDEX uq_essay_content_idempotency_partial
        ON essay_states (batch_id, text_storage_id)
        WHERE text_storage_id IS NOT NULL
    """)


def downgrade() -> None:
    """Restore the original unique constraint (for testing only)."""

    # Remove the partial unique index
    op.drop_index("uq_essay_content_idempotency_partial", table_name="essay_states")

    # Restore the original unique constraint
    # Note: This may fail if there are multiple NULL text_storage_id rows
    op.create_unique_constraint(
        "uq_essay_content_idempotency", "essay_states", ["batch_id", "text_storage_id"]
    )
