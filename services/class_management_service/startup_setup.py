from __future__ import annotations

from huleedu_service_libs.logging_utils import create_service_logger
from quart import Quart
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from services.class_management_service.config import Settings
from services.class_management_service.models_db import Base

logger = create_service_logger("cms.startup")


async def initialize_database_schema(app: Quart, settings: Settings) -> AsyncEngine:
    """Initialize the database schema and return the engine for health checks."""
    try:
        logger.info("Initializing database schema...")

        if not settings.DATABASE_URL:
            raise ValueError("DATABASE_URL is required but not configured")

        engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            future=True,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=settings.DATABASE_POOL_PRE_PING,
            pool_recycle=settings.DATABASE_POOL_RECYCLE,
        )

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Store engine on app for health checks
        app.database_engine = engine

        logger.info("Database schema initialized successfully")
        return engine
    except Exception as e:
        logger.critical(f"Failed to initialize database schema: {e}", exc_info=True)
        raise


async def shutdown_services() -> None:
    """Gracefully shutdown all services."""
    logger.info("Class Management Service shutdown completed")
