"""Database infrastructure management for Batch Orchestrator Service PostgreSQL implementation."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from config import Settings
from huleedu_service_libs.logging_utils import create_service_logger
from models_db import Base
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class BatchDatabaseInfrastructure:
    """
    Handles database infrastructure setup and session management.

    Provides connection pooling, session management, and schema initialization
    for the PostgreSQL batch repository implementation.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize database infrastructure with connection settings."""
        self.settings = settings
        self.logger = create_service_logger("bos.repository.infrastructure")

        # Create async engine with connection pooling
        self.engine = create_async_engine(
            settings.database_url,
            echo=False,
            future=True,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_pre_ping=True,  # Validate connections before use
        )

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
