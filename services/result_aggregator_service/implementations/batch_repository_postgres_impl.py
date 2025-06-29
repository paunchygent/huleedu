"""PostgreSQL implementation of batch repository."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from common_core.status_enums import BatchStatus, ProcessingStage

from ..models_db import BatchResult, EssayResult
from ..protocols import BatchRepositoryProtocol

logger = create_service_logger("result_aggregator.batch_repository")


class BatchRepositoryPostgresImpl(BatchRepositoryProtocol):
    """PostgreSQL implementation of batch repository."""

    def __init__(self, session: AsyncSession):
        """Initialize with database session."""
        self.session = session

    async def get_batch(self, batch_id: str) -> Optional[BatchResult]:
        """Get batch with all essay results."""
        result = await self.session.execute(
            select(BatchResult)
            .where(BatchResult.batch_id == batch_id)
            .options(selectinload(BatchResult.essays))
        )
        return result.scalars().first()

    async def get_user_batches(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[BatchResult]:
        """Get all batches for a user."""
        from sqlalchemy.orm import selectinload

        query = (
            select(BatchResult)
            .where(BatchResult.user_id == user_id)
            .options(selectinload(BatchResult.essays))  # Eagerly load essays
        )

        if status:
            query = query.where(BatchResult.overall_status == BatchStatus(status))

        query = query.order_by(BatchResult.created_at.desc()).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_batch(
        self,
        batch_id: str,
        user_id: str,
        essay_count: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BatchResult:
        """Create a new batch result."""
        batch = BatchResult(
            batch_id=batch_id,
            user_id=user_id,
            essay_count=essay_count,
            batch_metadata=metadata or {},
            overall_status=BatchStatus.AWAITING_CONTENT_VALIDATION,
        )
        self.session.add(batch)
        await self.session.commit()
        return batch

    async def update_batch_status(
        self, batch_id: str, status: str, error: Optional[str] = None
    ) -> bool:
        """Update batch status."""
        batch = await self.get_batch(batch_id)
        if not batch:
            logger.warning("Batch not found for status update", batch_id=batch_id)
            return False

        batch.overall_status = BatchStatus(status)
        if error:
            batch.last_error = error
            batch.error_count += 1
        batch.updated_at = datetime.utcnow()
        await self.session.commit()
        return True

    async def create_or_update_batch(
        self,
        batch_id: str,
        user_id: str,
        essay_count: int,
        requested_pipeline: Optional[str] = None,
    ) -> BatchResult:
        """Create or update batch entry."""
        # Try to get existing batch
        existing = await self.get_batch(batch_id)

        if existing:
            # Update existing
            existing.essay_count = essay_count
            existing.requested_pipeline = requested_pipeline
            existing.updated_at = datetime.utcnow()
        else:
            # Create new
            batch = BatchResult(
                batch_id=batch_id,
                user_id=user_id,
                essay_count=essay_count,
                requested_pipeline=requested_pipeline,
                overall_status=BatchStatus.AWAITING_CONTENT_VALIDATION,
            )
            self.session.add(batch)
            existing = batch

        await self.session.commit()
        return existing

    async def update_batch_phase_completed(
        self,
        batch_id: str,
        phase: str,
        completed_count: int,
        failed_count: int,
    ) -> None:
        """Update batch after phase completion."""
        batch = await self.get_batch(batch_id)
        if not batch:
            logger.warning("Batch not found for phase update", batch_id=batch_id)
            return

        # Update counts
        batch.completed_essay_count = completed_count
        batch.failed_essay_count = failed_count

        # Set processing_started_at if not already set
        if not batch.processing_started_at:
            batch.processing_started_at = datetime.utcnow()

        # Update status based on completion
        if completed_count + failed_count >= batch.essay_count:
            if failed_count == 0:
                batch.overall_status = BatchStatus.COMPLETED_SUCCESSFULLY
            else:
                batch.overall_status = BatchStatus.COMPLETED_WITH_FAILURES
            batch.processing_completed_at = datetime.utcnow()
        else:
            batch.overall_status = BatchStatus.PROCESSING_PIPELINES

        batch.updated_at = datetime.utcnow()
        await self.session.commit()

    async def update_batch_failed(self, batch_id: str, error_message: str) -> None:
        """Mark batch as failed."""
        batch = await self.get_batch(batch_id)
        if not batch:
            logger.warning("Batch not found for failure update", batch_id=batch_id)
            return

        batch.overall_status = BatchStatus.FAILED_CRITICALLY
        batch.last_error = error_message
        batch.error_count += 1
        batch.processing_completed_at = datetime.utcnow()
        batch.updated_at = datetime.utcnow()
        await self.session.commit()

    async def update_essay_spellcheck_result(
        self,
        essay_id: str,
        batch_id: str,
        status: ProcessingStage,
        correction_count: Optional[int] = None,
        corrected_text_storage_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update spellcheck results for an essay."""
        # Get or create essay result
        result = await self.session.execute(
            select(EssayResult).where(
                EssayResult.essay_id == essay_id, EssayResult.batch_id == batch_id
            )
        )
        essay = result.scalars().first()

        if not essay:
            essay = EssayResult(essay_id=essay_id, batch_id=batch_id)
            self.session.add(essay)

        # Update spellcheck fields
        essay.spellcheck_status = status
        essay.spellcheck_correction_count = correction_count
        essay.spellcheck_corrected_text_storage_id = corrected_text_storage_id
        essay.spellcheck_completed_at = datetime.utcnow()
        essay.spellcheck_error = error
        essay.updated_at = datetime.utcnow()

        await self.session.commit()

    async def update_essay_cj_assessment_result(
        self,
        essay_id: str,
        batch_id: str,
        status: ProcessingStage,
        rank: Optional[int] = None,
        score: Optional[float] = None,
        comparison_count: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update CJ assessment results for an essay."""
        # Get or create essay result
        result = await self.session.execute(
            select(EssayResult).where(
                EssayResult.essay_id == essay_id, EssayResult.batch_id == batch_id
            )
        )
        essay = result.scalars().first()

        if not essay:
            essay = EssayResult(essay_id=essay_id, batch_id=batch_id)
            self.session.add(essay)

        # Update CJ assessment fields
        essay.cj_assessment_status = status
        essay.cj_rank = rank
        essay.cj_score = score
        essay.cj_comparison_count = comparison_count
        essay.cj_assessment_completed_at = datetime.utcnow()
        essay.cj_assessment_error = error
        essay.updated_at = datetime.utcnow()

        await self.session.commit()
