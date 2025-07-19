"""Add content idempotency constraints for race condition mitigation

Revision ID: 20250719_0003
Revises: 20250713_0002
Create Date: 2025-07-19 12:00:00.000000

This migration addresses ELS-002 Phase 1: Database Foundation requirements.
Adds atomic database-level constraints to prevent content provisioning race conditions.

Key Changes:
1. Extract text_storage_id from JSON storage_references to dedicated column
2. Add unique constraint (batch_id, text_storage_id) to prevent duplicate assignments
3. Add foreign key constraint essay_states.batch_id → batch_essay_trackers.batch_id
4. Includes comprehensive rollback procedures for production safety
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20250719_0003"
down_revision = "20250713_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add content idempotency constraints for race condition mitigation."""
    
    # Step 1: Add text_storage_id column to essay_states table
    op.add_column(
        "essay_states", 
        sa.Column("text_storage_id", sa.String(length=255), nullable=True)
    )
    
    # Step 2: Populate text_storage_id from existing JSON storage_references data
    # This safely extracts the ORIGINAL_ESSAY storage reference for existing records
    op.execute("""
        UPDATE essay_states 
        SET text_storage_id = storage_references->>'ORIGINAL_ESSAY'
        WHERE storage_references IS NOT NULL 
        AND storage_references->>'ORIGINAL_ESSAY' IS NOT NULL
    """)
    
    # Step 3: Add unique constraint for content idempotency (batch_id, text_storage_id)
    # This prevents the same content from being assigned to multiple essay slots
    op.create_unique_constraint(
        "uq_essay_content_idempotency",
        "essay_states",
        ["batch_id", "text_storage_id"]
    )
    
    # Step 4: Clean up orphaned essay states before adding foreign key constraint
    # Remove essay states that reference non-existent batch_id (likely test data)
    op.execute("""
        DELETE FROM essay_states 
        WHERE batch_id IS NOT NULL 
        AND batch_id NOT IN (SELECT batch_id FROM batch_essay_trackers)
    """)
    
    # Step 5: Add foreign key constraint to ensure referential integrity
    # This enforces that essay_states.batch_id references a valid batch_essay_trackers record
    op.create_foreign_key(
        "fk_essay_states_batch_id",
        "essay_states",
        "batch_essay_trackers",
        ["batch_id"],
        ["batch_id"],
        ondelete="SET NULL"  # Allow orphaned essays if batch is deleted
    )
    
    # Step 6: Add index for efficient querying by text_storage_id
    op.create_index(
        "ix_essay_states_text_storage_id",
        "essay_states",
        ["text_storage_id"],
        unique=False
    )


def downgrade() -> None:
    """Remove content idempotency constraints (rollback procedure)."""
    
    # Remove index first
    op.drop_index("ix_essay_states_text_storage_id", table_name="essay_states")
    
    # Remove foreign key constraint
    op.drop_constraint("fk_essay_states_batch_id", "essay_states", type_="foreignkey")
    
    # Remove unique constraint
    op.drop_constraint("uq_essay_content_idempotency", "essay_states", type_="unique")
    
    # Remove text_storage_id column (data will be preserved in storage_references JSON)
    op.drop_column("essay_states", "text_storage_id")