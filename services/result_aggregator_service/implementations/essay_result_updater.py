"""Essay result update operations for Result Aggregator Service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from common_core.models.error_models import ErrorDetail
from common_core.status_enums import ProcessingStage
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select

from services.result_aggregator_service.models_db import EssayResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = create_service_logger("result_aggregator.essay_updater")


class EssayResultUpdater:
    """Handles essay result update operations."""

    def __init__(self, session_factory: async_sessionmaker):
        """Initialize with session factory.

        Args:
            session_factory: SQLAlchemy async session factory
        """
        self.session_factory = session_factory
        self.logger = logger

    async def update_essay_spellcheck_result(
        self,
        essay_id: str,
        batch_id: str,
        status: ProcessingStage,
        correlation_id: UUID,
        correction_count: Optional[int] = None,
        corrected_text_storage_id: Optional[str] = None,
        error_detail: Optional[ErrorDetail] = None,
    ) -> None:
        """Update essay spellcheck results.

        Args:
            essay_id: ID of the essay to update
            batch_id: ID of the batch containing the essay
            status: Processing stage status
            correlation_id: Correlation ID for tracking
            correction_count: Optional number of corrections made
            corrected_text_storage_id: Optional storage ID for corrected text
            error_detail: Optional error detail
        """
        async with self.session_factory() as session:
            # Find essay by essay_id only (not batch_id) to handle orphaned essays
            result = await session.execute(
                select(EssayResult).where(EssayResult.essay_id == essay_id)
            )
            essay = result.scalars().first()

            if not essay:
                # Create new essay if it doesn't exist
                essay = EssayResult(
                    essay_id=essay_id,
                    batch_id=batch_id,
                    spellcheck_status=status,
                )
                session.add(essay)
                self.logger.info(
                    "Created new essay result for spellcheck",
                    essay_id=essay_id,
                    batch_id=batch_id,
                )
            else:
                # Update existing essay
                essay.spellcheck_status = status
                # Associate with batch if not already associated
                if essay.batch_id is None:
                    essay.batch_id = batch_id
                    self.logger.info(
                        "Associated orphaned essay with batch during spellcheck update",
                        essay_id=essay_id,
                        batch_id=batch_id,
                    )

            # Update spellcheck-specific fields
            if correction_count is not None:
                essay.spellcheck_correction_count = correction_count
            if corrected_text_storage_id:
                essay.spellcheck_corrected_text_storage_id = corrected_text_storage_id
            if error_detail:
                essay.spellcheck_error_detail = error_detail.model_dump(mode="json")

            essay.updated_at = datetime.now(UTC).replace(tzinfo=None)
            await session.commit()

    async def update_essay_spellcheck_result_with_metrics(
        self,
        essay_id: str,
        batch_id: str,
        status: ProcessingStage,
        correlation_id: UUID,
        correction_count: Optional[int] = None,
        corrected_text_storage_id: Optional[str] = None,
        error_detail: Optional[ErrorDetail] = None,
        # Enhanced metrics from rich event
        l2_corrections: Optional[int] = None,
        spell_corrections: Optional[int] = None,
        word_count: Optional[int] = None,
        correction_density: Optional[float] = None,
        processing_duration_ms: Optional[int] = None,
    ) -> None:
        """Update essay spellcheck results with enhanced metrics from rich event.

        Args:
            essay_id: ID of the essay to update
            batch_id: ID of the batch containing the essay
            status: Processing stage status
            correlation_id: Correlation ID for tracking
            correction_count: Optional number of corrections made
            corrected_text_storage_id: Optional storage ID for corrected text
            error_detail: Optional error detail
            l2_corrections: Number of L2 dictionary corrections
            spell_corrections: Number of general spelling corrections
            word_count: Total word count
            correction_density: Corrections per 100 words
            processing_duration_ms: Processing duration in milliseconds
        """
        async with self.session_factory() as session:
            # Find essay by essay_id only (not batch_id) to handle orphaned essays
            result = await session.execute(
                select(EssayResult).where(EssayResult.essay_id == essay_id)
            )
            essay = result.scalars().first()

            if not essay:
                # Create new essay if it doesn't exist
                essay = EssayResult(
                    essay_id=essay_id,
                    batch_id=batch_id,
                    spellcheck_status=status,
                )
                session.add(essay)
                self.logger.info(
                    "Created new essay result for spellcheck with metrics",
                    essay_id=essay_id,
                    batch_id=batch_id,
                )
            else:
                # Update existing essay
                essay.spellcheck_status = status
                # Associate with batch if not already associated
                if essay.batch_id is None:
                    essay.batch_id = batch_id
                    self.logger.info(
                        "Associated orphaned essay with batch during spellcheck update",
                        essay_id=essay_id,
                        batch_id=batch_id,
                    )

            # Update spellcheck-specific fields
            if correction_count is not None:
                essay.spellcheck_correction_count = correction_count
            if corrected_text_storage_id:
                essay.spellcheck_corrected_text_storage_id = corrected_text_storage_id
            if error_detail:
                essay.spellcheck_error_detail = error_detail.model_dump(mode="json")

            # Store enhanced metrics in metadata field
            if any(
                [
                    l2_corrections is not None,
                    spell_corrections is not None,
                    word_count is not None,
                    correction_density is not None,
                    processing_duration_ms is not None,
                ]
            ):
                spellcheck_metrics = {
                    "l2_corrections": l2_corrections,
                    "spell_corrections": spell_corrections,
                    "word_count": word_count,
                    "correction_density": correction_density,
                    "processing_duration_ms": processing_duration_ms,
                }
                # Store in metadata field (JSON column)
                if essay.essay_metadata is None:
                    essay.essay_metadata = {}
                essay.essay_metadata["spellcheck_metrics"] = spellcheck_metrics

                self.logger.info(
                    "Updated essay with enhanced spellcheck metrics",
                    essay_id=essay_id,
                    batch_id=batch_id,
                    metrics=spellcheck_metrics,
                )

            essay.updated_at = datetime.now(UTC).replace(tzinfo=None)
            await session.commit()

    async def update_essay_cj_assessment_result(
        self,
        essay_id: str,
        batch_id: str,
        status: ProcessingStage,
        correlation_id: UUID,
        rank: Optional[int] = None,
        score: Optional[float] = None,
        comparison_count: Optional[int] = None,
        error_detail: Optional[ErrorDetail] = None,
    ) -> None:
        """Update essay CJ assessment results.

        Args:
            essay_id: ID of the essay to update
            batch_id: ID of the batch containing the essay
            status: Processing stage status
            correlation_id: Correlation ID for tracking
            rank: Optional rank of the essay
            score: Optional score of the essay
            comparison_count: Optional number of comparisons made
            error_detail: Optional error detail
        """
        async with self.session_factory() as session:
            # Find essay by essay_id only (not batch_id) to handle orphaned essays
            result = await session.execute(
                select(EssayResult).where(EssayResult.essay_id == essay_id)
            )
            essay = result.scalars().first()

            if not essay:
                # Create new essay if it doesn't exist
                essay = EssayResult(
                    essay_id=essay_id,
                    batch_id=batch_id,
                    cj_assessment_status=status,
                )
                session.add(essay)
                self.logger.info(
                    "Created new essay result for CJ assessment",
                    essay_id=essay_id,
                    batch_id=batch_id,
                )
            else:
                # Update existing essay
                essay.cj_assessment_status = status
                # Associate with batch if not already associated
                if essay.batch_id is None:
                    essay.batch_id = batch_id
                    self.logger.info(
                        "Associated orphaned essay with batch during CJ assessment update",
                        essay_id=essay_id,
                        batch_id=batch_id,
                    )

            # Update CJ-specific fields
            if rank is not None:
                essay.cj_rank = rank
            if score is not None:
                essay.cj_score = score
            if comparison_count is not None:
                essay.cj_comparison_count = comparison_count
            if error_detail:
                essay.cj_assessment_error_detail = error_detail.model_dump(mode="json")

            essay.updated_at = datetime.now(UTC).replace(tzinfo=None)
            await session.commit()

    async def update_essay_file_mapping(
        self,
        essay_id: str,
        file_upload_id: str,
        text_storage_id: Optional[str] = None,
    ) -> None:
        """Update essay with file_upload_id for traceability.

        Args:
            essay_id: Essay identifier
            file_upload_id: File upload identifier for traceability
            text_storage_id: Optional text storage identifier
        """
        async with self.session_factory() as session:
            # Check if essay exists, if not create it
            result = await session.execute(
                select(EssayResult).where(EssayResult.essay_id == essay_id)
            )
            essay = result.scalars().first()

            if essay:
                # Update existing essay
                essay.file_upload_id = file_upload_id
                if text_storage_id:
                    essay.original_text_storage_id = text_storage_id
                essay.updated_at = datetime.now(UTC).replace(tzinfo=None)
            else:
                # Create new essay record without batch association
                # This handles the case where slot assignment happens before batch registration
                essay = EssayResult(
                    essay_id=essay_id,
                    batch_id=None,  # No batch association yet - will be updated
                    # when batch is registered
                    file_upload_id=file_upload_id,
                    original_text_storage_id=text_storage_id,
                )
                session.add(essay)

            await session.commit()

            self.logger.info(
                "Updated essay file mapping",
                essay_id=essay_id,
                file_upload_id=file_upload_id,
                is_new=essay is None,
            )

    async def associate_essay_with_batch(
        self,
        essay_id: str,
        batch_id: str,
    ) -> None:
        """Associate an orphaned essay with its batch.

        Args:
            essay_id: Essay identifier
            batch_id: Batch identifier to associate
        """
        async with self.session_factory() as session:
            # Update essay with batch association
            result = await session.execute(
                select(EssayResult).where(
                    (EssayResult.essay_id == essay_id)
                    & (EssayResult.batch_id.is_(None))  # Only update if not already associated
                )
            )
            essay = result.scalars().first()

            if essay:
                essay.batch_id = batch_id
                essay.updated_at = datetime.now(UTC).replace(tzinfo=None)
                await session.commit()

                self.logger.info(
                    "Associated essay with batch",
                    essay_id=essay_id,
                    batch_id=batch_id,
                )
