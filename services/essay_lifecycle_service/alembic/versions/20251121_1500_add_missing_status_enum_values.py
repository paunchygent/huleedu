"""Add missing EssayStatus enum values for pipeline phases

Revision ID: e4f6a8b0c2d3
Revises: d3e5f8a9b1c2
Create Date: 2025-11-21 15:00:00.000000

This migration adds 29 EssayStatus enum values that exist in Python code but were
never added to the database. These values support fine-grained pipeline tracking
across content ingestion, spellcheck, NLP, AI feedback, editor revision, grammar
check, and CJ assessment phases.

Root Cause: Python enum was redesigned for detailed state tracking, but migrations
were never created to synchronize the database enum.

Impact: Eliminates InvalidTextRepresentationError in get_status_counts() queries
and enables future pipeline phase implementation.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4f6a8b0c2d3"
down_revision: str = "d3e5f8a9b1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add all missing EssayStatus enum values to essay_status_enum.

    Adds 29 values organized by pipeline phase:
    - Pipeline management: ready_for_processing
    - Content ingestion: content_ingesting, content_ingestion_failed
    - Spellcheck phase: awaiting_spellcheck, spellchecking_in_progress, spellchecked_success, spellcheck_failed
    - NLP phase: awaiting_nlp, nlp_processing_in_progress, nlp_success, nlp_failed
    - AI feedback phase: awaiting_ai_feedback, ai_feedback_processing_in_progress, ai_feedback_success, ai_feedback_failed
    - Editor revision phase: awaiting_editor_revision, editor_revision_processing_in_progress, editor_revision_success, editor_revision_failed
    - Grammar check phase: awaiting_grammar_check, grammar_check_processing_in_progress, grammar_check_success, grammar_check_failed
    - CJ assessment phase: awaiting_cj_assessment, cj_assessment_processing_in_progress, cj_assessment_success, cj_assessment_failed
    - Terminal states: all_processing_completed, essay_critical_failure

    Uses ADD VALUE IF NOT EXISTS for idempotency (PostgreSQL 9.6+).
    """
    # Pipeline Management
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'ready_for_processing';")
    )

    # Content Ingestion Phase
    op.execute(sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'content_ingesting';"))
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'content_ingestion_failed';")
    )

    # Spellcheck Phase
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'awaiting_spellcheck';")
    )
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'spellchecking_in_progress';")
    )
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'spellchecked_success';")
    )
    op.execute(sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'spellcheck_failed';"))

    # NLP Phase
    op.execute(sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'awaiting_nlp';"))
    op.execute(
        sa.text(
            "ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'nlp_processing_in_progress';"
        )
    )
    op.execute(sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'nlp_success';"))
    op.execute(sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'nlp_failed';"))

    # AI Feedback Phase
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'awaiting_ai_feedback';")
    )
    op.execute(
        sa.text(
            "ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'ai_feedback_processing_in_progress';"
        )
    )
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'ai_feedback_success';")
    )
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'ai_feedback_failed';")
    )

    # Editor Revision Phase
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'awaiting_editor_revision';")
    )
    op.execute(
        sa.text(
            "ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'editor_revision_processing_in_progress';"
        )
    )
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'editor_revision_success';")
    )
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'editor_revision_failed';")
    )

    # Grammar Check Phase
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'awaiting_grammar_check';")
    )
    op.execute(
        sa.text(
            "ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'grammar_check_processing_in_progress';"
        )
    )
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'grammar_check_success';")
    )
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'grammar_check_failed';")
    )

    # CJ Assessment Phase
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'awaiting_cj_assessment';")
    )
    op.execute(
        sa.text(
            "ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'cj_assessment_processing_in_progress';"
        )
    )
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'cj_assessment_success';")
    )
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'cj_assessment_failed';")
    )

    # Terminal States
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'all_processing_completed';")
    )
    op.execute(
        sa.text("ALTER TYPE essay_status_enum ADD VALUE IF NOT EXISTS 'essay_critical_failure';")
    )


def downgrade() -> None:
    """PostgreSQL does not support removing enum values.

    Downgrading would require:
    1. Creating new enum type without the values
    2. Migrating all data to new type (checking for any essays using these statuses)
    3. Dropping old type and renaming new type

    This is complex, risky, and rarely needed. If cleanup is required, create a
    forward migration that:
    1. Identifies essays using deprecated statuses
    2. Migrates them to appropriate replacement statuses
    3. Documents that old enum values remain but are unused
    """
    raise NotImplementedError(
        "Removing enum values is not supported. PostgreSQL enum values cannot be safely "
        "removed once added. If cleanup is needed, create a forward migration to migrate "
        "data away from deprecated statuses and document them as unused."
    )
