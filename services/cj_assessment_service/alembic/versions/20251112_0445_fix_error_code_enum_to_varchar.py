"""fix error_code enum to varchar

Revision ID: 52a8b9c3e4f1
Revises: 20251110_1200
Create Date: 2025-11-12 04:45:00.000000

Convert error_code column from PostgreSQL ENUM to VARCHAR(100) for flexibility.

Background:
- Original migration created 'errorcode' ENUM with 27 hardcoded values
- SQLAlchemy model defines error_code as String(100)
- Runtime writes ErrorCode enum values as strings
- Result: Type mismatch error when writing to database

Solution:
- Convert column to VARCHAR(100) using USING clause
- Drop 'errorcode' ENUM type
- Enables adding new error codes without migration
- Aligns database schema with SQLAlchemy model

Testing:
Per rule 085.4, this migration is tested by:
- services/cj_assessment_service/tests/integration/test_error_code_migration.py
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "52a8b9c3e4f1"
down_revision = "20251110_1200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Convert error_code from ENUM to VARCHAR(100).

    Steps:
    1. Convert column type using USING clause to cast ENUM values to text
    2. Drop the errorcode ENUM type (safe after column conversion)
    """
    # Convert error_code column from ENUM to VARCHAR(100)
    # USING clause converts existing ENUM values to text
    op.execute(
        """
        ALTER TABLE cj_comparison_pairs
        ALTER COLUMN error_code TYPE VARCHAR(100)
        USING error_code::text;
    """
    )

    # Drop the ENUM type (no longer needed)
    op.execute("DROP TYPE IF EXISTS errorcode;")


def downgrade() -> None:
    """
    Recreate ENUM type and convert column back (rollback path).

    WARNING: This rollback only supports the original 27 error codes.
    New error codes added after this migration will fail the rollback.
    """
    # Recreate the errorcode ENUM with original values
    op.execute(
        """
        CREATE TYPE errorcode AS ENUM (
            'UNKNOWN_ERROR',
            'VALIDATION_ERROR',
            'RESOURCE_NOT_FOUND',
            'CONFIGURATION_ERROR',
            'EXTERNAL_SERVICE_ERROR',
            'KAFKA_PUBLISH_ERROR',
            'CONTENT_SERVICE_ERROR',
            'SPELLCHECK_SERVICE_ERROR',
            'NLP_SERVICE_ERROR',
            'AI_FEEDBACK_SERVICE_ERROR',
            'CJ_ASSESSMENT_SERVICE_ERROR',
            'MISSING_REQUIRED_FIELD',
            'INVALID_CONFIGURATION',
            'TIMEOUT',
            'CONNECTION_ERROR',
            'SERVICE_UNAVAILABLE',
            'RATE_LIMIT',
            'QUOTA_EXCEEDED',
            'AUTHENTICATION_ERROR',
            'INVALID_API_KEY',
            'INVALID_REQUEST',
            'INVALID_RESPONSE',
            'PARSING_ERROR',
            'CIRCUIT_BREAKER_OPEN',
            'REQUEST_QUEUED',
            'PROCESSING_ERROR',
            'INITIALIZATION_FAILED'
        );
    """
    )

    # Convert column back to ENUM type
    op.execute(
        """
        ALTER TABLE cj_comparison_pairs
        ALTER COLUMN error_code TYPE errorcode
        USING error_code::errorcode;
    """
    )
