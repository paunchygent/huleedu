"""PostgreSQL implementation of batch repository."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from huleedu_service_libs.database import DatabaseMetricsProtocol
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload

from common_core.status_enums import BatchStatus, ProcessingStage
from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.models_db import Base, BatchResult, EssayResult
from services.result_aggregator_service.protocols import BatchRepositoryProtocol

logger = create_service_logger("result_aggregator.batch_repository")


class BatchRepositoryPostgresImpl(BatchRepositoryProtocol):
    """PostgreSQL implementation of batch repository with internal
    session management and metrics."""

    def __init__(
        self,
        settings: Settings,
        metrics: Optional[DatabaseMetricsProtocol] = None,
        engine: Optional[AsyncEngine] = None,
    ):
        """Initialize with settings and database engine."""
        self.settings = settings
        self.logger = logger
        self.metrics = metrics

        # Use provided engine or create new one
        if engine:
            self.engine = engine
        else:
            # Create async engine with connection pooling
            self.engine = create_async_engine(
                settings.DATABASE_URL,
                echo=False,
                future=True,
                pool_size=settings.DATABASE_POOL_SIZE,
                max_overflow=settings.DATABASE_MAX_OVERFLOW,
                pool_pre_ping=True,
                pool_recycle=3600,  # Recycle connections after 1 hour
            )

        # Create session maker
        self.async_session_maker = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def initialize_schema(self) -> None:
        """Create database tables if they don't exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.logger.info("Database schema initialized")

    def _record_operation_metrics(
        self,
        operation: str,
        table: str,
        duration: float,
        success: bool = True,
    ) -> None:
        """Record database operation metrics."""
        if self.metrics:
            self.metrics.record_query_duration(
                operation=operation,
                table=table,
                duration=duration,
                success=success,
            )

    def _record_error_metrics(self, error_type: str, operation: str) -> None:
        """Record database error metrics."""
        if self.metrics:
            self.metrics.record_database_error(error_type, operation)

    @asynccontextmanager
    async def _get_session(self) -> AsyncIterator[AsyncSession]:
        """Get a database session with proper transaction handling."""
        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def get_batch(self, batch_id: str) -> Optional[BatchResult]:
        """Get batch with all essay results."""
        start_time = time.time()
        operation = "get_batch"
        table = "batch_results"
        success = True

        try:
            async with self._get_session() as session:
                result = await session.execute(
                    select(BatchResult)
                    .where(BatchResult.batch_id == batch_id)
                    .options(selectinload(BatchResult.essays))
                )
                return result.scalars().first()

        except Exception as e:
            success = False
            error_type = e.__class__.__name__
            self._record_error_metrics(error_type, operation)
            self.logger.error(f"Failed to get batch {batch_id}: {error_type}: {e}")
            raise

        finally:
            duration = time.time() - start_time
            self._record_operation_metrics(operation, table, duration, success)

    async def get_user_batches(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[BatchResult]:
        """Get all batches for a user."""
        async with self._get_session() as session:
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

    async def create_batch(
        self,
        batch_id: str,
        user_id: str,
        essay_count: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BatchResult:
        """Create a new batch result."""
        async with self._get_session() as session:
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

    async def update_batch_status(
        self, batch_id: str, status: str, error: Optional[str] = None
    ) -> bool:
        """Update batch status.

        Args:
            batch_id: ID of the batch to update
            status: Status as string (will be converted to BatchStatus)
            error: Optional error message

        Returns:
            bool: True if update was successful, False if batch not found
        """
        try:
            # Convert string status to BatchStatus enum
            batch_status = BatchStatus(status) if isinstance(status, str) else status

            async with self._get_session() as session:
                result = await session.execute(
                    select(BatchResult).where(BatchResult.batch_id == batch_id)
                )
                batch = result.scalars().first()

                if not batch:
                    return False

                batch.overall_status = batch_status
                if error:
                    batch.last_error = error
                batch.updated_at = datetime.utcnow()

                await session.commit()
                return True

        except ValueError as e:
            self.logger.error(f"Invalid status value: {status}. Error: {e}")
            return False

    async def update_essay_spellcheck_result(
        self,
        essay_id: str,
        batch_id: str,
        status: ProcessingStage,
        correction_count: Optional[int] = None,
        corrected_text_storage_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update essay spellcheck results.

        Args:
            essay_id: ID of the essay to update
            batch_id: ID of the batch containing the essay
            status: Processing stage status
            correction_count: Optional number of corrections made
            corrected_text_storage_id: Optional storage ID for corrected text
            error: Optional error message
        """
        async with self._get_session() as session:
            # Find or create essay result
            result = await session.execute(
                select(EssayResult).where(
                    EssayResult.essay_id == essay_id, EssayResult.batch_id == batch_id
                )
            )
            essay = result.scalars().first()

            if not essay:
                essay = EssayResult(
                    essay_id=essay_id,
                    batch_id=batch_id,
                    spellcheck_status=status,
                )
                session.add(essay)
            else:
                essay.spellcheck_status = status

            # Update spellcheck-specific fields
            if correction_count is not None:
                essay.spellcheck_correction_count = correction_count
            if corrected_text_storage_id:
                essay.spellcheck_corrected_text_storage_id = corrected_text_storage_id
            if error:
                essay.spellcheck_error = error

            essay.updated_at = datetime.utcnow()
            await session.commit()

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
        """Update essay CJ assessment results.

        Args:
            essay_id: ID of the essay to update
            batch_id: ID of the batch containing the essay
            status: Processing stage status
            rank: Optional rank of the essay
            score: Optional score of the essay
            comparison_count: Optional number of comparisons made
            error: Optional error message
        """
        async with self._get_session() as session:
            # Find or create essay result
            result = await session.execute(
                select(EssayResult).where(
                    EssayResult.essay_id == essay_id, EssayResult.batch_id == batch_id
                )
            )
            essay = result.scalars().first()

            if not essay:
                essay = EssayResult(
                    essay_id=essay_id,
                    batch_id=batch_id,
                    cj_assessment_status=status,
                )
                session.add(essay)
            else:
                essay.cj_assessment_status = status

            # Update CJ-specific fields
            if rank is not None:
                essay.cj_rank = rank
            if score is not None:
                essay.cj_score = score
            if comparison_count is not None:
                essay.cj_comparison_count = comparison_count
            if error:
                essay.cj_assessment_error = error

            essay.updated_at = datetime.utcnow()
            await session.commit()

    async def update_batch_phase_completed(
        self,
        batch_id: str,
        phase: str,
        completed_count: int,
        failed_count: int,
    ) -> None:
        """Update batch after phase completion."""
        async with self._get_session() as session:
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
                    "completed_at": datetime.utcnow().isoformat(),
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

                batch.updated_at = datetime.utcnow()
                await session.commit()

    async def update_batch_failed(self, batch_id: str, error_message: str) -> None:
        """Mark batch as failed."""
        async with self._get_session() as session:
            result = await session.execute(
                select(BatchResult).where(BatchResult.batch_id == batch_id)
            )
            batch = result.scalars().first()

            if batch:
                batch.overall_status = BatchStatus.FAILED_CRITICALLY
                batch.last_error = error_message
                batch.updated_at = datetime.utcnow()
                await session.commit()
