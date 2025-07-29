"""PostgreSQL repository implementation for NLP Service.

Follows async SQLAlchemy pattern with session management and basic CRUD operations.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncGenerator
from uuid import uuid4

from common_core.status_enums import ProcessingStatus
from huleedu_service_libs.error_handling import (
    raise_connection_error,
    raise_processing_error,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from services.nlp_service.models_db import Base, NlpAnalysisJob

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger("nlp_service.repository")


class NlpRepository:
    """Repository for NLP analysis job persistence."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Initialize repository with database engine.

        Args:
            engine: SQLAlchemy async engine for database access
        """
        self.engine = engine
        self._async_session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide a transactional scope for database operations.

        Yields:
            AsyncSession: Database session for operations

        Raises:
            ConnectionError: If database connection fails
        """
        async with self._async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                _LOGGER.error(f"Database session error: {str(e)}")
                raise_connection_error(
                    service="nlp_service",
                    operation="database_session",
                    target="postgresql",
                    message=f"Session error: {str(e)}",
                    correlation_id=uuid4()
                )

    async def initialize_db_schema(self) -> None:
        """Create database tables if they don't exist (idempotent)."""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            _LOGGER.info("Database schema initialized successfully")
        except Exception as e:
            _LOGGER.error(f"Failed to initialize database schema: {str(e)}")
            raise_connection_error(
                service="nlp_service",
                operation="schema_initialization",
                target="postgresql",
                message=f"Schema initialization failed: {str(e)}",
                correlation_id=uuid4()
            )

    async def create_nlp_job(
        self,
        batch_id: str,
        essay_id: str,
        analysis_type: str = "student_matching",
    ) -> NlpAnalysisJob:
        """Create a new NLP analysis job.

        Args:
            batch_id: Unique batch identifier
            essay_id: Essay ID to analyze
            analysis_type: Type of NLP analysis

        Returns:
            Created NlpAnalysisJob instance

        Raises:
            ProcessingError: If job creation fails
        """
        try:
            async with self.get_session() as session:
                job = NlpAnalysisJob(
                    batch_id=batch_id,
                    essay_id=essay_id,
                    analysis_type=analysis_type,
                )
                session.add(job)
                await session.flush()
                _LOGGER.info(f"Created NLP job for batch: {batch_id}, essay: {essay_id}")
                return job
        except Exception as e:
            _LOGGER.error(f"Failed to create NLP job: {str(e)}")
            raise_processing_error(
                service="nlp_service",
                operation="create_nlp_job",
                message=f"Failed to create job: {str(e)}",
                correlation_id=uuid4(),
                reason="nlp_job_creation_failed"
            )

    async def get_nlp_job_by_batch(self, batch_id: str) -> NlpAnalysisJob | None:
        """Retrieve NLP job by batch ID.

        Args:
            batch_id: Unique batch identifier

        Returns:
            NlpAnalysisJob if found, None otherwise

        Raises:
            ConnectionError: If database query fails
        """
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(NlpAnalysisJob).where(NlpAnalysisJob.batch_id == batch_id)
                )
                job = result.scalar_one_or_none()
                if job:
                    _LOGGER.debug(f"Found NLP job for batch: {batch_id}")
                else:
                    _LOGGER.debug(f"No NLP job found for batch: {batch_id}")
                return job
        except Exception as e:
            _LOGGER.error(f"Failed to retrieve NLP job: {str(e)}")
            raise_connection_error(
                service="nlp_service",
                operation="nlp_job_retrieval",
                target="postgresql",
                message=f"Failed to get job: {str(e)}",
                correlation_id=uuid4()
            )

    async def update_job_status(
        self,
        job_id: str,
        status: ProcessingStatus,
        error_detail: dict | None = None,
    ) -> None:
        """Update NLP job status and optionally error details.

        Args:
            job_id: NLP job ID (UUID)
            status: New status value (ProcessingStatus enum)
            error_detail: Optional error details to store

        Raises:
            ProcessingError: If update fails
        """
        try:
            async with self.get_session() as session:
                job = await session.get(NlpAnalysisJob, job_id)
                if not job:
                    raise_processing_error(
                        service="nlp_service",
                        operation="update_job_status",
                        message=f"Job {job_id} not found",
                        correlation_id=uuid4(),
                        reason="nlp_job_not_found"
                    )

                job.status = status
                if error_detail:
                    job.error_detail = error_detail

                await session.flush()
                _LOGGER.info(f"Updated NLP job {job_id} status to: {status.value}")
        except Exception as e:
            if "nlp_job_not_found" not in str(e):
                _LOGGER.error(f"Failed to update job status: {str(e)}")
                raise_processing_error(
                    service="nlp_service",
                    operation="update_job_status",
                    message=f"Failed to update status: {str(e)}",
                    correlation_id=uuid4(),
                    reason="status_update_failed"
                )
