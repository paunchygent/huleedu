"""PostgreSQL implementation of batch repository."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from common_core.status_enums import BatchStatus, ProcessingStage
from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.models_db import Base, BatchResult, EssayResult
from services.result_aggregator_service.protocols import BatchRepositoryProtocol

logger = create_service_logger("result_aggregator.batch_repository")


class BatchRepositoryPostgresImpl(BatchRepositoryProtocol):
    """PostgreSQL implementation of batch repository with internal session management."""

    def __init__(self, settings: Settings):
        """Initialize with settings and create database engine."""
        self.settings = settings
        self.logger = logger

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
        async with self._get_session() as session:
            result = await session.execute(
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
        async with self._get_session() as session:
            query = (
                select(BatchResult)
                .where(BatchResult.user_id == user_id)
                .options(selectinload(BatchResult.essays))  # Eagerly load essays
            )

            if status:
                query = query.where(BatchResult.status == status)

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
                status=BatchStatus.PENDING.value,
                essay_count=essay_count,
                completed_count=0,
                failed_count=0,
                metadata=metadata or {},
            )
            session.add(batch)
            await session.commit()
            await session.refresh(batch)
            return batch

    async def update_batch_status(
        self, batch_id: str, status: str, error: Optional[str] = None
    ) -> bool:
        """Update batch status."""
        async with self._get_session() as session:
            result = await session.execute(
                select(BatchResult).where(BatchResult.batch_id == batch_id)
            )
            batch = result.scalars().first()

            if not batch:
                return False

            batch.status = status
            if error:
                batch.error_message = error
            batch.updated_at = datetime.now(UTC)

            await session.commit()
            return True

    async def update_essay_spellcheck_result(
        self,
        essay_id: str,
        batch_id: str,
        status: ProcessingStage,
        correction_count: Optional[int] = None,
        corrected_text_storage_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update essay spellcheck results."""
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
                    spellcheck_status=status.value,
                )
                session.add(essay)
            else:
                essay.spellcheck_status = status.value

            # Update spellcheck-specific fields
            if correction_count is not None:
                essay.correction_count = correction_count
            if corrected_text_storage_id:
                essay.corrected_text_storage_id = corrected_text_storage_id
            if error:
                essay.spellcheck_error = error

            essay.updated_at = datetime.now(UTC)
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
        """Update essay CJ assessment results."""
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
                    cj_assessment_status=status.value,
                )
                session.add(essay)
            else:
                essay.cj_assessment_status = status.value

            # Update CJ-specific fields
            if rank is not None:
                essay.rank = rank
            if score is not None:
                essay.score = score
            if comparison_count is not None:
                essay.comparison_count = comparison_count
            if error:
                essay.cj_assessment_error = error

            essay.updated_at = datetime.now(UTC)
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
                phases_completed = batch.metadata.get("phases_completed", {})
                phases_completed[phase] = {
                    "completed_count": completed_count,
                    "failed_count": failed_count,
                    "completed_at": datetime.now(UTC).isoformat(),
                }
                batch.metadata["phases_completed"] = phases_completed

                # Update overall counts based on all phases
                # Note: This assumes phases can have overlapping essays
                batch.completed_count = max(batch.completed_count, completed_count)
                batch.failed_count = max(batch.failed_count, failed_count)

                # Check if all processing is complete
                total_processed = completed_count + failed_count
                if total_processed >= batch.essay_count:
                    # Determine overall status
                    if failed_count == 0:
                        batch.status = BatchStatus.COMPLETED.value
                    elif completed_count == 0:
                        batch.status = BatchStatus.FAILED.value
                    else:
                        batch.status = BatchStatus.PARTIALLY_COMPLETED.value

                batch.updated_at = datetime.now(UTC)
                await session.commit()

    async def update_batch_failed(self, batch_id: str, error_message: str) -> None:
        """Mark batch as failed."""
        async with self._get_session() as session:
            result = await session.execute(
                select(BatchResult).where(BatchResult.batch_id == batch_id)
            )
            batch = result.scalars().first()

            if batch:
                batch.status = BatchStatus.FAILED.value
                batch.error_message = error_message
                batch.updated_at = datetime.now(UTC)
                await session.commit()