from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import create_async_engine

from services.class_management_service.config import Settings
from services.class_management_service.models_db import Base

logger = create_service_logger("cms.startup")


async def initialize_database_schema(settings: Settings) -> None:
    """Initialize the database schema using the provided engine."""
    try:
        logger.info("Initializing database schema...")
        engine = create_async_engine(settings.DATABASE_URL)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()
        logger.info("Database schema initialized successfully")
    except Exception as e:
        logger.critical(f"Failed to initialize database schema: {e}", exc_info=True)
        raise


async def shutdown_services() -> None:
    """Gracefully shutdown all services."""
    logger.info("Class Management Service shutdown completed")
