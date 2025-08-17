"""
PostgreSQL batch state repository implementation for BCS.

Provides persistent storage for essay processing state with database transactions.
Used as fallback for Redis operations and permanent audit trail.
"""

from __future__ import annotations

from datetime import UTC, datetime
from time import time

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tenacity import retry, stop_after_attempt, wait_exponential

from huleedu_service_libs.logging_utils import create_service_logger
from services.batch_conductor_service.metrics import (
    DB_OPERATION_DURATION,
    DB_OPERATION_ERRORS,
)
from services.batch_conductor_service.models_db import PhaseCompletion
from services.batch_conductor_service.protocols import BatchStateRepositoryProtocol

logger = create_service_logger("bcs.postgres_repository")


class PostgreSQLBatchStateRepositoryImpl(BatchStateRepositoryProtocol):
    """
    PostgreSQL implementation for permanent storage of batch processing state.

    Provides database persistence with transactions for audit trail and reprocessing.

    DATA RETENTION STRATEGY:
    - Phase completions are PERMANENT records (never deleted)
    - Serves as audit trail for compliance and debugging
    - Enables dependency resolution even months after completion
    - No TTL or cleanup required - storage is minimal (batch_id, phase, timestamp)
    - If archival is needed in future, consider partitioning by year

    PRODUCTION HARDENING:
    - Connection pooling: pool_size=10, max_overflow=20
    - Retry logic: 3 attempts with exponential backoff (2-10 seconds)
    - Health checks: Integrated with /healthz endpoint
    - Metrics: Prometheus histograms for operation duration and error counters
    """

    def __init__(self, database_url: str):
        """Initialize the PostgreSQL repository with connection settings."""
        self.database_url = database_url

        # Create async engine with connection pooling
        self.engine = create_async_engine(
            database_url,
            echo=False,
            future=True,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
        )

        # Create session maker
        self.async_session = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def record_essay_step_completion(
        self, batch_id: str, essay_id: str, step_name: str, metadata: dict | None = None
    ) -> bool:
        """
        Record essay step completion in PostgreSQL.

        Currently a placeholder implementation.
        """
        logger.info(
            f"PostgreSQL: Recorded completion for batch={batch_id}, "
            f"essay={essay_id}, step={step_name}",
            extra={"batch_id": batch_id, "essay_id": essay_id, "step_name": step_name},
        )
        return True

    async def get_essay_completed_steps(self, batch_id: str, essay_id: str) -> set[str]:
        """Get completed steps for an essay from PostgreSQL."""
        # Placeholder implementation
        return set()

    async def get_batch_completion_summary(self, batch_id: str) -> dict[str, dict[str, int]]:
        """Get batch completion summary from PostgreSQL."""
        # Placeholder implementation
        return {}

    async def is_batch_step_complete(self, batch_id: str, step_name: str) -> bool:
        """
        Check if batch step is complete using PostgreSQL phase_completions data.

        A step is considered complete if it has a record in phase_completions
        with completed=True for the given batch.

        Args:
            batch_id: Batch identifier
            step_name: Phase/step name to check

        Returns:
            True if the step is completed for this batch, False otherwise
        """
        try:
            async with self.async_session() as session:
                stmt = select(PhaseCompletion.completed).where(
                    and_(
                        PhaseCompletion.batch_id == batch_id,
                        PhaseCompletion.phase_name == step_name,
                        PhaseCompletion.completed,
                    )
                )

                result = await session.execute(stmt)
                completion_record = result.first()

                is_complete = completion_record is not None

                logger.debug(
                    f"PostgreSQL: Step {step_name} completion check for batch {batch_id}: {is_complete}",
                    extra={
                        "batch_id": batch_id,
                        "step_name": step_name,
                        "is_complete": is_complete,
                    },
                )

                return is_complete

        except Exception as e:
            logger.error(
                f"PostgreSQL: Failed to check step completion for batch {batch_id}, step {step_name}: {e}",
                extra={"batch_id": batch_id, "step_name": step_name, "error": str(e)},
                exc_info=True,
            )
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def record_batch_phase_completion(
        self, batch_id: str, phase_name: str, completed: bool
    ) -> bool:
        """
        Record phase completion status in PostgreSQL for permanent storage.

        This provides the permanent audit trail that persists forever, enabling
        dependency resolution even weeks or months after the phase completed.

        Args:
            batch_id: Batch identifier
            phase_name: Name of the completed phase
            completed: Whether the phase completed successfully

        Returns:
            True if recorded successfully, False otherwise
        """
        start_time = time()
        try:
            async with self.async_session() as session:
                async with session.begin():
                    # Use INSERT ON CONFLICT for idempotency
                    stmt = insert(PhaseCompletion).values(
                        batch_id=batch_id,
                        phase_name=phase_name,
                        completed=completed,
                        completed_at=datetime.now(UTC),
                        phase_metadata={"recorded_by": "bcs", "source": "event"},
                    )

                    # On conflict, update the completion status and timestamp
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["batch_id", "phase_name"],
                        set_={
                            "completed": stmt.excluded.completed,
                            "completed_at": stmt.excluded.completed_at,
                            "phase_metadata": stmt.excluded.phase_metadata,
                        },
                    )

                    await session.execute(stmt)
                    await session.commit()

                    # Record metrics
                    if DB_OPERATION_DURATION:
                        DB_OPERATION_DURATION.labels(operation="record_phase_completion").observe(
                            time() - start_time
                        )

                    logger.info(
                        f"PostgreSQL: Persisted phase {phase_name} completion for batch {batch_id} "
                        f"(completed={completed})",
                        extra={
                            "batch_id": batch_id,
                            "phase_name": phase_name,
                            "completed": completed,
                        },
                    )
                    return True

        except IntegrityError as e:
            if DB_OPERATION_ERRORS:
                DB_OPERATION_ERRORS.labels(
                    operation="record_phase_completion", error_type="integrity_error"
                ).inc()
            # This shouldn't happen with ON CONFLICT, but handle it gracefully
            logger.warning(
                f"PostgreSQL: Integrity error recording phase completion for batch {batch_id}, "
                f"phase {phase_name}: {e}",
                extra={"batch_id": batch_id, "phase_name": phase_name, "error": str(e)},
            )
            return True  # Consider it success since the record exists

        except Exception as e:
            if DB_OPERATION_ERRORS:
                DB_OPERATION_ERRORS.labels(
                    operation="record_phase_completion", error_type="general_error"
                ).inc()
            logger.error(
                f"PostgreSQL: Failed to record phase completion for batch {batch_id}, "
                f"phase {phase_name}: {e}",
                extra={"batch_id": batch_id, "phase_name": phase_name, "error": str(e)},
                exc_info=True,
            )
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def get_completed_phases(self, batch_id: str) -> set[str]:
        """
        Get all completed phases for a batch from PostgreSQL.

        This is used for dependency resolution when Redis cache is empty.

        Args:
            batch_id: Batch identifier

        Returns:
            Set of phase names that have completed successfully
        """
        start_time = time()
        try:
            async with self.async_session() as session:
                stmt = select(PhaseCompletion.phase_name).where(
                    and_(
                        PhaseCompletion.batch_id == batch_id,
                        PhaseCompletion.completed,
                    )
                )

                result = await session.execute(stmt)
                completed_phases = {row[0] for row in result}

                # Record metrics
                if DB_OPERATION_DURATION:
                    DB_OPERATION_DURATION.labels(operation="get_completed_phases").observe(
                        time() - start_time
                    )

                logger.debug(
                    f"PostgreSQL: Retrieved {len(completed_phases)} completed phases for batch {batch_id}",
                    extra={"batch_id": batch_id, "phase_count": len(completed_phases)},
                )

                return completed_phases

        except Exception as e:
            if DB_OPERATION_ERRORS:
                DB_OPERATION_ERRORS.labels(
                    operation="get_completed_phases", error_type="general_error"
                ).inc()
            logger.error(
                f"PostgreSQL: Failed to get completed phases for batch {batch_id}: {e}",
                extra={"batch_id": batch_id, "error": str(e)},
                exc_info=True,
            )
            return set()


    async def close(self) -> None:
        """Close the database connection pool."""
        await self.engine.dispose()
        logger.info("PostgreSQL repository connection pool closed")
