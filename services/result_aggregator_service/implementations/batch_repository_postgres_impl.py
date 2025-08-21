"""PostgreSQL implementation facade for batch repository."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import UUID

from common_core.models.error_models import ErrorDetail
from common_core.status_enums import ProcessingStage
from huleedu_service_libs.logging_utils import create_service_logger

from services.result_aggregator_service.implementations.batch_repository_mappers import (
    BatchRepositoryMappers,
)
from services.result_aggregator_service.implementations.batch_repository_queries import (
    BatchRepositoryQueries,
)
from services.result_aggregator_service.implementations.batch_statistics_calculator import (
    BatchStatisticsCalculator,
)
from services.result_aggregator_service.implementations.essay_result_updater import (
    EssayResultUpdater,
)
from services.result_aggregator_service.models_db import BatchResult, EssayResult
from services.result_aggregator_service.protocols import BatchRepositoryProtocol

if TYPE_CHECKING:
    from huleedu_service_libs.database import DatabaseMetricsProtocol
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = create_service_logger("result_aggregator.batch_repository")


class BatchRepositoryPostgresImpl(BatchRepositoryProtocol):
    """PostgreSQL implementation facade for batch repository."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        metrics: Optional[DatabaseMetricsProtocol] = None,
    ):
        """Initialize with session factory and metrics.

        Args:
            session_factory: SQLAlchemy async session factory (injected from DI)
            metrics: Optional database metrics for observability
        """
        self.session_factory = session_factory
        self.metrics = metrics
        self.logger = logger

        # Initialize specialized components
        self.queries = BatchRepositoryQueries(session_factory)
        self.essay_updater = EssayResultUpdater(session_factory)
        self.statistics = BatchStatisticsCalculator(session_factory)
        self.mappers = BatchRepositoryMappers()

    async def initialize_schema(self) -> None:
        """Initialize database schema if needed."""
        # Schema initialization is handled at the service level
        pass

    def _record_operation_metrics(
        self,
        operation: str,
        table: str,
        duration: float,
        success: bool,
    ) -> None:
        """Record operation metrics if metrics collector is available."""
        if self.metrics:
            self.metrics.record_query_duration(
                operation=operation,
                table=table,
                duration=duration,
                success=success,
            )

    def _record_error_metrics(self, error_type: str, operation: str) -> None:
        """Record error metrics if metrics collector is available."""
        if self.metrics:
            self.metrics.record_database_error(error_type=error_type, operation=operation)

    # ========== Query Operations (Delegate to BatchRepositoryQueries) ==========

    async def get_batch(self, batch_id: str) -> Optional[BatchResult]:
        """Get batch with all essay results."""
        start_time = time.time()
        operation = "get_batch"
        table = "batch_results"
        success = True

        try:
            return await self.queries.get_batch(batch_id)

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
        return await self.queries.get_user_batches(user_id, status, limit, offset)

    async def create_batch(
        self,
        batch_id: str,
        user_id: str,
        essay_count: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BatchResult:
        """Create a new batch result."""
        return await self.queries.create_batch(batch_id, user_id, essay_count, metadata)

    async def get_batch_essays(self, batch_id: str) -> List[EssayResult]:
        """Get all essays for a batch."""
        start_time = time.perf_counter()

        try:
            essays = await self.queries.get_batch_essays(batch_id)

            duration = time.perf_counter() - start_time
            self._record_operation_metrics(
                operation="get_batch_essays",
                table="essay_results",
                duration=duration,
                success=True,
            )

            return essays

        except Exception as e:
            duration = time.perf_counter() - start_time
            self._record_operation_metrics(
                operation="get_batch_essays",
                table="essay_results",
                duration=duration,
                success=False,
            )
            self._record_error_metrics(type(e).__name__, "get_batch_essays")
            self.logger.error(
                "Failed to get batch essays",
                batch_id=batch_id,
                error=str(e),
                exc_info=True,
            )
            raise

    # ========== Status Update Operations (Delegate to BatchStatisticsCalculator) ==========

    async def update_batch_status(
        self,
        batch_id: str,
        status: str,
        error_detail: Optional[ErrorDetail] = None,
        correlation_id: Optional[UUID] = None,
    ) -> bool:
        """Update batch status."""
        return await self.statistics.update_batch_status(
            batch_id, status, error_detail, correlation_id
        )

    async def set_batch_processing_started(self, batch_id: str) -> None:
        """Set the processing_started_at timestamp for a batch."""
        await self.statistics.set_batch_processing_started(batch_id)

    async def update_batch_phase_completed(
        self,
        batch_id: str,
        phase: str,
        completed_count: int,
        failed_count: int,
    ) -> None:
        """Update batch after phase completion."""
        await self.statistics.update_batch_phase_completed(
            batch_id, phase, completed_count, failed_count
        )

    async def update_batch_failed(
        self, batch_id: str, error_detail: ErrorDetail, correlation_id: UUID
    ) -> None:
        """Mark batch as failed."""
        await self.statistics.update_batch_failed(batch_id, error_detail, correlation_id)

    async def mark_batch_completed(
        self,
        batch_id: str,
        final_status: str,
        completion_stats: dict,
    ) -> None:
        """Mark batch as completed with final statistics."""
        try:
            await self.statistics.mark_batch_completed(batch_id, final_status, completion_stats)

        except Exception as e:
            self._record_error_metrics(type(e).__name__, "mark_batch_completed")
            self.logger.error(
                "Failed to mark batch as completed",
                batch_id=batch_id,
                error=str(e),
                exc_info=True,
            )
            raise

    # ========== Essay Update Operations (Delegate to EssayResultUpdater) ==========

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
        """Update essay spellcheck results."""
        await self.essay_updater.update_essay_spellcheck_result(
            essay_id,
            batch_id,
            status,
            correlation_id,
            correction_count,
            corrected_text_storage_id,
            error_detail,
        )

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
        """Update essay with detailed spellcheck metrics."""
        await self.essay_updater.update_essay_spellcheck_result_with_metrics(
            essay_id,
            batch_id,
            status,
            correlation_id,
            correction_count,
            corrected_text_storage_id,
            error_detail,
            l2_corrections,
            spell_corrections,
            word_count,
            correction_density,
            processing_duration_ms,
        )

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
        """Update essay CJ assessment results."""
        await self.essay_updater.update_essay_cj_assessment_result(
            essay_id,
            batch_id,
            status,
            correlation_id,
            rank,
            score,
            comparison_count,
            error_detail,
        )

    async def update_essay_file_mapping(
        self,
        essay_id: str,
        file_upload_id: str,
        text_storage_id: Optional[str] = None,
    ) -> None:
        """Update essay with file_upload_id for traceability."""
        start_time = time.perf_counter()
        try:
            await self.essay_updater.update_essay_file_mapping(
                essay_id, file_upload_id, text_storage_id
            )

            duration = time.perf_counter() - start_time
            self._record_operation_metrics(
                operation="update_essay_file_mapping",
                table="essay_results",
                duration=duration,
                success=True,
            )

        except Exception as e:
            duration = time.perf_counter() - start_time
            self._record_operation_metrics(
                operation="update_essay_file_mapping",
                table="essay_results",
                duration=duration,
                success=False,
            )
            self._record_error_metrics(type(e).__name__, "update_essay_file_mapping")
            self.logger.error(
                "Failed to update essay file mapping",
                essay_id=essay_id,
                error=str(e),
                exc_info=True,
            )
            raise

    async def associate_essay_with_batch(
        self,
        essay_id: str,
        batch_id: str,
    ) -> None:
        """Associate an orphaned essay with its batch."""
        start_time = time.perf_counter()
        try:
            await self.essay_updater.associate_essay_with_batch(essay_id, batch_id)

            duration = time.perf_counter() - start_time
            self._record_operation_metrics(
                operation="associate_essay_with_batch",
                table="essay_results",
                duration=duration,
                success=True,
            )

        except Exception as e:
            duration = time.perf_counter() - start_time
            self._record_operation_metrics(
                operation="associate_essay_with_batch",
                table="essay_results",
                duration=duration,
                success=False,
            )
            self._record_error_metrics(type(e).__name__, "associate_essay_with_batch")
            self.logger.error(
                "Failed to associate essay with batch",
                essay_id=essay_id,
                batch_id=batch_id,
                error=str(e),
                exc_info=True,
            )
            raise
