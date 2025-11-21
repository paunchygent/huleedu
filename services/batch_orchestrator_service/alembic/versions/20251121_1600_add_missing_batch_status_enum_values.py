"""Add missing batch_status_enum values

Revision ID: 20251121_1600
Revises: 20250808_0400_b602bb2e74f4
Create Date: 2025-11-21 16:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f7a9b1c3d5"
down_revision: Union[str, None] = "b602bb2e74f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing batch_status_enum values to match Python BatchStatus enum."""
    # Database currently has only 6 values:
    # - awaiting_content_validation
    # - processing
    # - completed
    # - failed
    # - cancelled
    # - student_validation_completed
    #
    # Python enum (libs/common_core/src/common_core/status_enums.py) has 12 values.
    # Adding the 6 missing values:

    # Critical for GUEST batch flow
    op.execute(
        "ALTER TYPE batch_status_enum ADD VALUE IF NOT EXISTS 'ready_for_pipeline_execution'"
    )
    op.execute("ALTER TYPE batch_status_enum ADD VALUE IF NOT EXISTS 'processing_pipelines'")

    # Pipeline configuration and validation states
    op.execute(
        "ALTER TYPE batch_status_enum ADD VALUE IF NOT EXISTS 'awaiting_pipeline_configuration'"
    )
    op.execute("ALTER TYPE batch_status_enum ADD VALUE IF NOT EXISTS 'awaiting_student_validation'")
    op.execute(
        "ALTER TYPE batch_status_enum ADD VALUE IF NOT EXISTS 'validation_timeout_processed'"
    )

    # Terminal states (more granular than generic "completed"/"failed")
    op.execute("ALTER TYPE batch_status_enum ADD VALUE IF NOT EXISTS 'completed_successfully'")
    op.execute("ALTER TYPE batch_status_enum ADD VALUE IF NOT EXISTS 'completed_with_failures'")
    op.execute("ALTER TYPE batch_status_enum ADD VALUE IF NOT EXISTS 'failed_critically'")
    op.execute("ALTER TYPE batch_status_enum ADD VALUE IF NOT EXISTS 'content_ingestion_failed'")


def downgrade() -> None:
    """Downgrade not supported for enum values (PostgreSQL limitation)."""
    # PostgreSQL does not support removing enum values
    # Manual intervention required if rollback needed
    pass
