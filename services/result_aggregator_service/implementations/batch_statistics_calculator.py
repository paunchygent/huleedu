"""Batch statistics calculation for Result Aggregator Service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Dict, Optional
from uuid import UUID

from common_core.models.error_models import ErrorDetail
from common_core.status_enums import BatchStatus
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select, update

from services.result_aggregator_service.models_db import BatchResult, EssayResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = create_service_logger("result_aggregator.statistics")


class BatchStatisticsCalculator:
    """Calculates batch statistics and aggregations."""

    def __init__(self, session_factory: async_sessionmaker):
        """Initialize with session factory.

        Args:
            session_factory: SQLAlchemy async session factory
        """
        self.session_factory = session_factory
        self.logger = logger

    async def update_batch_status(
        self,
        batch_id: str,
        status: str,
        error_detail: Optional[ErrorDetail] = None,
        correlation_id: Optional[UUID] = None,
    ) -> bool:
        """Update batch status.

        Args:
            batch_id: ID of the batch to update
            status: Status as string (will be converted to BatchStatus)
            error_detail: Optional error detail
            correlation_id: Optional correlation ID for tracking

        Returns:
            bool: True if update was successful, False if batch not found
        """
        try:
            # Convert string status to BatchStatus enum
            batch_status = BatchStatus(status) if isinstance(status, str) else status

            async with self.session_factory() as session:
                result = await session.execute(
                    select(BatchResult).where(BatchResult.batch_id == batch_id)
                )
                batch = result.scalars().first()

                if not batch:
                    return False

                batch.overall_status = batch_status
                if error_detail:
                    batch.batch_error_detail = error_detail.model_dump(mode="json")
                batch.updated_at = datetime.now(UTC).replace(tzinfo=None)

                await session.commit()
                return True

        except ValueError as e:
            self.logger.error(f"Invalid status value: {status}. Error: {e}")
            return False

    async def set_batch_processing_started(self, batch_id: str) -> None:
        """Set the processing_started_at timestamp for a batch.

        Args:
            batch_id: Batch identifier
        """
        async with self.session_factory() as session:
            stmt = (
                update(BatchResult)
                .where(BatchResult.batch_id == batch_id)
                .values(processing_started_at=datetime.now(UTC).replace(tzinfo=None))
            )
            await session.execute(stmt)
            await session.commit()

    async def update_batch_phase_completed(
        self,
        batch_id: str,
        phase: str,
        completed_count: int,
        failed_count: int,
    ) -> None:
        """Update batch after phase completion.

        Args:
            batch_id: Batch identifier
            phase: Phase name (e.g., 'spellcheck', 'cj_assessment')
            completed_count: Number of essays completed successfully
            failed_count: Number of essays that failed
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(BatchResult).where(BatchResult.batch_id == batch_id)
            )
            batch = result.scalars().first()

            if batch:
                # Update phase-specific completion tracking
                phases_completed = (
                    batch.batch_metadata.get("phases_completed", {}) if batch.batch_metadata else {}
                )
                phases_completed[phase] = {
                    "completed_count": completed_count,
                    "failed_count": failed_count,
                    "completed_at": datetime.now(UTC).isoformat(),
                }
                if not batch.batch_metadata:
                    batch.batch_metadata = {}
                batch.batch_metadata["phases_completed"] = phases_completed

                # Update overall counts based on all phases
                # Note: This assumes phases can have overlapping essays
                batch.completed_essay_count = max(batch.completed_essay_count, completed_count)
                batch.failed_essay_count = max(batch.failed_essay_count, failed_count)

                # Check if all processing is complete
                total_processed = completed_count + failed_count
                if total_processed >= batch.essay_count:
                    # Determine overall status
                    if failed_count == 0:
                        batch.overall_status = BatchStatus.COMPLETED_SUCCESSFULLY
                    elif completed_count == 0:
                        batch.overall_status = BatchStatus.FAILED_CRITICALLY
                    else:
                        batch.overall_status = BatchStatus.COMPLETED_WITH_FAILURES

                batch.updated_at = datetime.now(UTC).replace(tzinfo=None)
                await session.commit()

    async def update_batch_failed(
        self, batch_id: str, error_detail: ErrorDetail, correlation_id: UUID
    ) -> None:
        """Mark batch as failed.

        Args:
            batch_id: Batch identifier
            error_detail: Error detail describing the failure
            correlation_id: Correlation ID for tracking
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(BatchResult).where(BatchResult.batch_id == batch_id)
            )
            batch = result.scalars().first()

            if batch:
                batch.overall_status = BatchStatus.FAILED_CRITICALLY
                batch.batch_error_detail = error_detail.model_dump(mode="json")
                batch.updated_at = datetime.now(UTC).replace(tzinfo=None)
                await session.commit()

    async def mark_batch_completed(
        self,
        batch_id: str,
        final_status: str,
        completion_stats: dict,
    ) -> None:
        """Mark batch as completed with final statistics.

        Args:
            batch_id: Batch identifier
            final_status: Final batch status
            completion_stats: Dictionary containing completion statistics
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(BatchResult).where(BatchResult.batch_id == batch_id)
            )
            batch = result.scalars().first()

            if not batch:
                self.logger.warning(f"Batch {batch_id} not found for completion marking")
                return

            # Update batch completion fields
            batch.overall_status = BatchStatus(final_status)
            batch.completed_essay_count = completion_stats.get("successful_essays", 0)
            batch.failed_essay_count = completion_stats.get("failed_essays", 0)
            batch.processing_completed_at = datetime.now(UTC).replace(tzinfo=None)
            batch.updated_at = datetime.now(UTC).replace(tzinfo=None)

            # Store completion statistics in batch metadata
            current_metadata = batch.batch_metadata or {}
            current_metadata.update(
                {
                    "completion_stats": completion_stats,
                    "completed_at": datetime.now(UTC).isoformat(),
                }
            )
            batch.batch_metadata = current_metadata

            await session.commit()

            self.logger.info(
                "Marked batch as completed",
                batch_id=batch_id,
                final_status=final_status,
                successful_essays=completion_stats.get("successful_essays", 0),
                failed_essays=completion_stats.get("failed_essays", 0),
            )

    async def calculate_phase_statistics(
        self,
        batch_id: str,
        phase: str,
    ) -> Dict[str, Any]:
        """Calculate statistics for a specific phase.

        Args:
            batch_id: Batch identifier
            phase: Phase name (e.g., 'spellcheck', 'cj_assessment')

        Returns:
            Dictionary containing phase statistics
        """
        async with self.session_factory() as session:
            if phase == "spellcheck":
                # Get all essays for the batch
                essays_result = await session.execute(
                    select(EssayResult).where(EssayResult.batch_id == batch_id)
                )
                essays = essays_result.scalars().all()

                successful = sum(
                    1
                    for e in essays
                    if e.spellcheck_status in ["COMPLETED", "CORRECTION_NOT_NEEDED"]
                )
                failed = sum(1 for e in essays if e.spellcheck_status == "FAILED")
                pending = sum(
                    1 for e in essays if e.spellcheck_status in ["PENDING", "IN_PROGRESS", None]
                )

                # Calculate metrics
                total_corrections = sum(e.spellcheck_correction_count or 0 for e in essays)
                avg_corrections = total_corrections / successful if successful > 0 else 0

                return {
                    "phase": "spellcheck",
                    "successful_count": successful,
                    "failed_count": failed,
                    "pending_count": pending,
                    "total_corrections": total_corrections,
                    "average_corrections": avg_corrections,
                }

            elif phase == "cj_assessment":
                # Get all essays for the batch
                essays_result = await session.execute(
                    select(EssayResult).where(EssayResult.batch_id == batch_id)
                )
                essays = essays_result.scalars().all()

                successful = sum(1 for e in essays if e.cj_assessment_status == "COMPLETED")
                failed = sum(1 for e in essays if e.cj_assessment_status == "FAILED")
                pending = sum(
                    1 for e in essays if e.cj_assessment_status in ["PENDING", "IN_PROGRESS", None]
                )

                # Calculate metrics
                avg_score = (
                    sum(e.cj_score or 0 for e in essays if e.cj_score is not None) / successful
                    if successful > 0
                    else 0
                )
                total_comparisons = sum(e.cj_comparison_count or 0 for e in essays)

                return {
                    "phase": "cj_assessment",
                    "successful_count": successful,
                    "failed_count": failed,
                    "pending_count": pending,
                    "average_score": avg_score,
                    "total_comparisons": total_comparisons,
                }

            return {
                "phase": phase,
                "successful_count": 0,
                "failed_count": 0,
                "pending_count": 0,
            }

    async def calculate_batch_completion_stats(
        self,
        batch_id: str,
    ) -> Dict[str, Any]:
        """Calculate overall batch completion statistics.

        Args:
            batch_id: Batch identifier

        Returns:
            Dictionary containing overall batch statistics
        """
        async with self.session_factory() as session:
            # Get batch
            batch_result = await session.execute(
                select(BatchResult).where(BatchResult.batch_id == batch_id)
            )
            batch = batch_result.scalars().first()

            if not batch:
                return {}

            # Get all essays
            essays_result = await session.execute(
                select(EssayResult).where(EssayResult.batch_id == batch_id)
            )
            essays = essays_result.scalars().all()

            # Calculate overall statistics
            total_essays = len(essays)

            # Count essays with all phases completed
            successful_essays = sum(
                1
                for e in essays
                if (
                    e.spellcheck_status in ["COMPLETED", "CORRECTION_NOT_NEEDED"]
                    and e.cj_assessment_status == "COMPLETED"
                )
            )

            # Count essays with any phase failed
            failed_essays = sum(
                1
                for e in essays
                if (e.spellcheck_status == "FAILED" or e.cj_assessment_status == "FAILED")
            )

            # Calculate processing duration
            duration = None
            if batch.processing_started_at and batch.processing_completed_at:
                duration = (
                    batch.processing_completed_at - batch.processing_started_at
                ).total_seconds()

            return {
                "batch_id": batch_id,
                "total_essays": total_essays,
                "successful_essays": successful_essays,
                "failed_essays": failed_essays,
                "partial_essays": total_essays - successful_essays - failed_essays,
                "success_rate": (successful_essays / total_essays * 100) if total_essays > 0 else 0,
                "processing_duration_seconds": duration,
                "phases_completed": batch.batch_metadata.get("phases_completed", {})
                if batch.batch_metadata
                else {},
            }

    async def get_batch_error_summary(
        self,
        batch_id: str,
    ) -> Dict[str, Any]:
        """Get error summary for a batch.

        Args:
            batch_id: Batch identifier

        Returns:
            Dictionary containing error summary
        """
        async with self.session_factory() as session:
            # Get all essays with errors
            essays_result = await session.execute(
                select(EssayResult).where(
                    (EssayResult.batch_id == batch_id)
                    & (
                        (EssayResult.spellcheck_error_detail.isnot(None))
                        | (EssayResult.cj_assessment_error_detail.isnot(None))
                    )
                )
            )
            essays_with_errors = essays_result.scalars().all()

            # Categorize errors
            spellcheck_errors = []
            cj_errors = []

            for essay in essays_with_errors:
                if essay.spellcheck_error_detail:
                    spellcheck_errors.append(
                        {
                            "essay_id": essay.essay_id,
                            "error": essay.spellcheck_error_detail,
                        }
                    )
                if essay.cj_assessment_error_detail:
                    cj_errors.append(
                        {
                            "essay_id": essay.essay_id,
                            "error": essay.cj_assessment_error_detail,
                        }
                    )

            return {
                "batch_id": batch_id,
                "total_errors": len(spellcheck_errors) + len(cj_errors),
                "spellcheck_errors": spellcheck_errors,
                "cj_assessment_errors": cj_errors,
            }
