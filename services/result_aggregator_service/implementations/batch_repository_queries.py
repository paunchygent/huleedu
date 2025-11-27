"""Database query operations for Result Aggregator Service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from services.result_aggregator_service.models_db import BatchResult, EssayResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = create_service_logger("result_aggregator.queries")


class BatchRepositoryQueries:
    """Handles database query operations for batches and essays."""

    def __init__(self, session_factory: async_sessionmaker):
        """Initialize with session factory.

        Args:
            session_factory: SQLAlchemy async session factory
        """
        self.session_factory = session_factory
        self.logger = logger

    async def get_batch(self, batch_id: str) -> Optional[BatchResult]:
        """Get batch with all essay results.

        Args:
            batch_id: The batch ID to retrieve

        Returns:
            BatchResult with essays loaded, or None if not found
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(BatchResult)
                .where(BatchResult.batch_id == batch_id)
                .options(selectinload(BatchResult.essays))
            )
            batch: Optional[BatchResult] = result.scalars().first()
            return batch

    async def create_batch(
        self,
        batch_id: str,
        user_id: str,
        essay_count: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BatchResult:
        """Create a new batch result.

        Args:
            batch_id: Unique batch identifier
            user_id: User who owns the batch
            essay_count: Total number of essays in batch
            metadata: Optional batch metadata

        Returns:
            Created BatchResult instance
        """
        from common_core.status_enums import BatchStatus

        async with self.session_factory() as session:
            batch = BatchResult(
                batch_id=batch_id,
                user_id=user_id,
                overall_status=BatchStatus.AWAITING_CONTENT_VALIDATION,
                essay_count=essay_count,
                completed_essay_count=0,
                failed_essay_count=0,
                batch_metadata=metadata or {},
            )
            session.add(batch)
            await session.commit()
            await session.refresh(batch)
            return batch

    async def get_user_batches(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[BatchResult]:
        """Get all batches for a user.

        Args:
            user_id: User ID to filter batches
            status: Optional status filter
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of BatchResult objects for the user
        """
        async with self.session_factory() as session:
            query = (
                select(BatchResult)
                .where(BatchResult.user_id == user_id)
                .options(selectinload(BatchResult.essays))  # Eagerly load essays
            )

            if status:
                query = query.where(BatchResult.overall_status == status)

            query = query.order_by(BatchResult.created_at.desc()).limit(limit).offset(offset)

            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_batch_essays(self, batch_id: str) -> List[EssayResult]:
        """Get all essays for a batch.

        Args:
            batch_id: The batch ID to get essays for

        Returns:
            List of EssayResult objects for the batch
        """
        async with self.session_factory() as session:
            # Query essays for the batch
            result = await session.execute(
                select(EssayResult)
                .where(EssayResult.batch_id == batch_id)
                .order_by(EssayResult.essay_id)
            )
            essays = result.scalars().all()

            self.logger.debug(
                "Retrieved batch essays",
                batch_id=batch_id,
                essay_count=len(essays),
            )

            return list(essays)

    async def get_or_create_essay(
        self,
        essay_id: str,
        batch_id: str,
    ) -> tuple[EssayResult, bool]:
        """Get existing essay or create new one.

        Args:
            essay_id: Essay identifier
            batch_id: Batch identifier

        Returns:
            Tuple of (EssayResult, created_flag)
        """
        async with self.session_factory() as session:
            # Try to get existing essay
            result = await session.execute(
                select(EssayResult).where(
                    (EssayResult.essay_id == essay_id) & (EssayResult.batch_id == batch_id)
                )
            )
            essay: Optional[EssayResult] = result.scalars().first()

            if essay:
                return essay, False

            # Create new essay if not found
            essay = EssayResult(
                essay_id=essay_id,
                batch_id=batch_id,
            )
            session.add(essay)
            await session.commit()
            await session.refresh(essay)
            return essay, True

    async def get_essay_by_id(
        self,
        essay_id: str,
        batch_id: Optional[str] = None,
    ) -> Optional[EssayResult]:
        """Get essay by ID with optional batch filter.

        Args:
            essay_id: Essay identifier
            batch_id: Optional batch identifier for filtering

        Returns:
            EssayResult if found, None otherwise
        """
        async with self.session_factory() as session:
            query = select(EssayResult).where(EssayResult.essay_id == essay_id)

            if batch_id:
                query = query.where(EssayResult.batch_id == batch_id)

            result = await session.execute(query)
            essay: Optional[EssayResult] = result.scalars().first()
            return essay

    async def update_batch_timestamps(
        self,
        batch_id: str,
        processing_started: bool = False,
        processing_completed: bool = False,
    ) -> None:
        """Update batch processing timestamps.

        Args:
            batch_id: Batch identifier
            processing_started: Set processing_started_at timestamp
            processing_completed: Set processing_completed_at timestamp
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(BatchResult).where(BatchResult.batch_id == batch_id)
            )
            batch: Optional[BatchResult] = result.scalars().first()

            if batch:
                if processing_started and not batch.processing_started_at:
                    batch.processing_started_at = datetime.now(UTC).replace(tzinfo=None)
                if processing_completed:
                    batch.processing_completed_at = datetime.now(UTC).replace(tzinfo=None)

                await session.commit()

    async def batch_exists(self, batch_id: str) -> bool:
        """Check if a batch exists.

        Args:
            batch_id: Batch identifier to check

        Returns:
            True if batch exists, False otherwise
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(BatchResult.batch_id).where(BatchResult.batch_id == batch_id)
            )
            return result.scalars().first() is not None

    async def get_batch_with_essays_count(
        self,
        batch_id: str,
    ) -> Optional[tuple[BatchResult, int]]:
        """Get batch with count of essays.

        Args:
            batch_id: Batch identifier

        Returns:
            Tuple of (BatchResult, essay_count) or None if not found
        """
        from sqlalchemy import func

        async with self.session_factory() as session:
            # Get batch
            batch_result = await session.execute(
                select(BatchResult).where(BatchResult.batch_id == batch_id)
            )
            batch: Optional[BatchResult] = batch_result.scalars().first()

            if not batch:
                return None

            # Count essays
            count_result = await session.execute(
                select(func.count(EssayResult.essay_id)).where(EssayResult.batch_id == batch_id)
            )
            essay_count = count_result.scalar() or 0

            return batch, essay_count

    async def get_batch_phase_status(
        self,
        batch_id: str,
        phase: str,
    ) -> Dict[str, int]:
        """Get status counts for a specific phase.

        Args:
            batch_id: Batch identifier
            phase: Phase name (spellcheck or cj_assessment)

        Returns:
            Dictionary with completed_count and failed_count
        """
        from sqlalchemy import func

        async with self.session_factory() as session:
            if phase == "spellcheck":
                # Count completed spellcheck
                completed_result = await session.execute(
                    select(func.count(EssayResult.essay_id)).where(
                        (EssayResult.batch_id == batch_id)
                        & (
                            EssayResult.spellcheck_status.in_(
                                [
                                    "COMPLETED",
                                    "CORRECTION_NOT_NEEDED",
                                ]
                            )
                        )
                    )
                )
                completed_count = completed_result.scalar() or 0

                # Count failed spellcheck
                failed_result = await session.execute(
                    select(func.count(EssayResult.essay_id)).where(
                        (EssayResult.batch_id == batch_id)
                        & (EssayResult.spellcheck_status == "FAILED")
                    )
                )
                failed_count = failed_result.scalar() or 0

            elif phase == "cj_assessment":
                # Count completed CJ assessment
                completed_result = await session.execute(
                    select(func.count(EssayResult.essay_id)).where(
                        (EssayResult.batch_id == batch_id)
                        & (EssayResult.cj_assessment_status == "COMPLETED")
                    )
                )
                completed_count = completed_result.scalar() or 0

                # Count failed CJ assessment
                failed_result = await session.execute(
                    select(func.count(EssayResult.essay_id)).where(
                        (EssayResult.batch_id == batch_id)
                        & (EssayResult.cj_assessment_status == "FAILED")
                    )
                )
                failed_count = failed_result.scalar() or 0
            else:
                completed_count = 0
                failed_count = 0

            return {
                "completed_count": completed_count,
                "failed_count": failed_count,
            }

    async def set_batch_assignment_id(
        self,
        batch_id: str,
        assignment_id: Optional[str],
    ) -> None:
        """Set assignment identifier for a batch if not already set.

        This method is intentionally idempotent: it only updates the record when
        a non-null assignment_id is provided and the current value is NULL.
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(BatchResult).where(BatchResult.batch_id == batch_id)
            )
            batch: Optional[BatchResult] = result.scalars().first()

            if not batch:
                return

            if assignment_id is not None and batch.assignment_id is None:
                batch.assignment_id = assignment_id
                await session.commit()
