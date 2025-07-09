from __future__ import annotations

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.quart_app import HuleEduApp
from sqlalchemy.ext.asyncio import AsyncEngine

from services.class_management_service.models_db import Base

logger = create_service_logger("cms.startup")


async def initialize_database_schema(app: HuleEduApp) -> AsyncEngine:
    """Initialize the database schema using the app's existing engine."""
    try:
        logger.info("Initializing database schema...")

        # Use the engine already set in create_app (guaranteed to exist)
        engine = app.database_engine

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("Database schema initialized successfully")
        return engine
    except Exception as e:
        logger.critical(f"Failed to initialize database schema: {e}", exc_info=True)
        raise


async def shutdown_services() -> None:
    """Gracefully shutdown all services."""
    try:
        # Shutdown Redis and other async resources
        from services.class_management_service.di import shutdown_container_resources

        await shutdown_container_resources()
        logger.info("Container resources shutdown completed")
    except Exception as e:
        logger.error(f"Error during container resource shutdown: {e}")

    logger.info("Class Management Service shutdown completed")
