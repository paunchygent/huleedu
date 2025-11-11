"""Database infrastructure management for Batch Orchestrator Service PostgreSQL implementation."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional

from huleedu_service_libs.database import DatabaseMetrics, setup_database_monitoring
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from services.batch_orchestrator_service.config import Settings
from services.batch_orchestrator_service.models_db import Base


class BatchDatabaseInfrastructure:
    """
    Handles database infrastructure setup and session management.

    Provides connection pooling, session management, and schema initialization
    for the PostgreSQL batch repository implementation.
    """

    def __init__(
        self, settings: Settings, database_metrics: Optional[DatabaseMetrics] = None
    ) -> None:
        """Initialize database infrastructure with connection settings and optional metrics."""
        self.settings = settings
        self.logger = create_service_logger("bos.repository.infrastructure")
        self.database_metrics = database_metrics

        # Create async engine with connection pooling
        self.engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            future=True,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_pre_ping=True,  # Validate connections before use
        )

        # Setup database monitoring if metrics are provided
        if self.database_metrics:
            setup_database_monitoring(self.engine, "bos", self.database_metrics.get_metrics())
            self.logger.info("Database monitoring enabled for BOS")

        # Create session maker
        self.async_session_maker = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def initialize_db_schema(self) -> None:
        """Create database tables if they don't exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.logger.info("Database schema initialized")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Context manager for database sessions with proper transaction handling."""
        session = self.async_session_maker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
