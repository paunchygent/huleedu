"""Startup and shutdown logic for CJ Assessment Service."""

from __future__ import annotations

from dishka import AsyncContainer
from huleedu_service_libs.database import DatabaseMetrics
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Quart

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.metrics import get_metrics
from services.cj_assessment_service.protocols import CJRepositoryProtocol

logger = create_service_logger("cj_assessment_service.startup")


async def initialize_services(app: Quart, settings: Settings, container: AsyncContainer) -> None:
    """Initialize database schema and metrics (DI container already initialized in app.py)."""
    try:
        # Initialize database schema directly (following BOS/ELS pattern)
        async with container() as request_container:
            database = await request_container.get(CJRepositoryProtocol)
            await database.initialize_db_schema()
            logger.info("Database schema initialized successfully")

            # Store database engine for health checks
            if hasattr(database, "engine"):
                setattr(app, "database_engine", database.engine)
                logger.info("Database engine stored for health checks")

            # Get database metrics for integration
            database_metrics = await request_container.get(DatabaseMetrics)

            # Get shared metrics with database metrics integration (thread-safe singleton pattern)
            metrics = get_metrics(database_metrics)

            # Store metrics in app context (proper Quart pattern)
            app.extensions = getattr(app, "extensions", {})
            app.extensions["metrics"] = metrics

        logger.info("HTTP metrics initialized and stored in app extensions")
        logger.info(f"Available HTTP metrics: {list(metrics.keys())}")

        logger.info(
            "CJ Assessment Service DI container and quart-dishka integration "
            "initialized successfully.",
        )
    except Exception as e:
        logger.critical(f"Failed to initialize CJ Assessment Service: {e}", exc_info=True)
        raise


async def shutdown_services() -> None:
    """Gracefully shutdown the service."""
    try:
        logger.info("CJ Assessment Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)
