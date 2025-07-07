"""PostgreSQL implementation of SpellcheckRepositoryProtocol.

Follows patterns used by other services (ELS, BOS) with async SQLAlchemy
engine, session management, and optional schema initialisation.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Iterable, Optional

from huleedu_service_libs.database import DatabaseMetricsProtocol
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload

from common_core.status_enums import SpellcheckJobStatus as SCJobStatus
from services.spell_checker_service.config import Settings
from services.spell_checker_service.models_db import (
    Base,
    SpellcheckJob,
    SpellcheckToken,
)
from services.spell_checker_service.repository_protocol import SpellcheckRepositoryProtocol

if TYPE_CHECKING:  # pragma: no cover
    pass

_LOGGER = logging.getLogger("spell_checker.repository.postgres")


class PostgreSQLSpellcheckRepository(SpellcheckRepositoryProtocol):
    """Production PostgreSQL repository for spell-checker jobs/tokens with database metrics."""

    def __init__(
        self,
        settings: Settings,
        metrics: Optional[DatabaseMetricsProtocol] = None,
        engine: Optional[AsyncEngine] = None,
    ) -> None:
        self.settings = settings
        self.metrics = metrics

        # Use provided engine or create new one
        if engine:
            self.engine = engine
        else:
            self.engine = create_async_engine(
                settings.database_url,
                echo=False,
                future=True,
                pool_size=getattr(settings, "DATABASE_POOL_SIZE", 5),
                max_overflow=getattr(settings, "DATABASE_MAX_OVERFLOW", 10),
                pool_pre_ping=getattr(settings, "DATABASE_POOL_PRE_PING", True),
                pool_recycle=getattr(settings, "DATABASE_POOL_RECYCLE", 1800),
            )

        self.async_session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

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

    async def initialize_db_schema(self) -> None:
        """Create database tables if they don't exist (idempotent)."""
        async with self.engine.begin() as conn:
            # Ensure pg_trgm extension required for GIN trigram index exists
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await conn.run_sync(Base.metadata.create_all)
        _LOGGER.info("Spell-checker DB schema initialised")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide a transactional session context."""
        session = self.async_session_maker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    # ---------------------------------------------------------------------
    # CRUD operations implementing the protocol
    # ---------------------------------------------------------------------
    async def create_job(
        self,
        batch_id: uuid.UUID,
        essay_id: uuid.UUID,
        *,
        language: str = "en",
    ) -> uuid.UUID:
        start_time = time.time()
        operation = "create_job"
        table = "spellcheck_jobs"
        success = True

        try:
            new_job_id = uuid.uuid4()
            async with self.session() as session:
                job = SpellcheckJob(
                    job_id=new_job_id,
                    batch_id=batch_id,
                    essay_id=essay_id,
                    language=language,
                )
                session.add(job)
            _LOGGER.debug("Created spellcheck job %s", new_job_id)
            return new_job_id

        except Exception as e:
            success = False
            error_type = e.__class__.__name__
            self._record_error_metrics(error_type, operation)
            _LOGGER.error(f"Failed to create spellcheck job: {error_type}: {e}")
            raise

        finally:
            duration = time.time() - start_time
            self._record_operation_metrics(operation, table, duration, success)

    async def update_status(
        self,
        job_id: uuid.UUID,
        status: SCJobStatus,
        *,
        error_message: str | None = None,
        processing_ms: int | None = None,
    ) -> None:
        async with self.session() as session:
            stmt = (
                update(SpellcheckJob)
                .where(SpellcheckJob.job_id == job_id)
                .values(
                    status=status,
                    error_message=error_message,
                    processing_ms=processing_ms,
                )
            )
            await session.execute(stmt)
        _LOGGER.debug("Updated job %s to status %s", job_id, status)

    async def add_tokens(
        self,
        job_id: uuid.UUID,
        tokens: Iterable[tuple[str, list[str] | None, int | None, str | None]],
    ) -> None:
        rows = [
            SpellcheckToken(
                job_id=job_id,
                token=t[0],
                suggestions=t[1],
                position=t[2],
                sentence=t[3],
            )
            for t in tokens
        ]
        async with self.session() as session:
            session.add_all(rows)
        _LOGGER.debug("Inserted %d tokens for job %s", len(rows), job_id)

    async def get_job(self, job_id: uuid.UUID) -> SpellcheckJob | None:  # type: ignore[name-defined]
        async with self.session() as session:
            result = await session.execute(
                select(SpellcheckJob)
                .options(selectinload(SpellcheckJob.tokens))
                .where(SpellcheckJob.job_id == job_id)
            )
            return result.scalars().first()
