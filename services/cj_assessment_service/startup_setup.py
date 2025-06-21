"""Startup and shutdown logic for CJ Assessment Service."""

from __future__ import annotations

from huleedu_service_libs.logging_utils import create_service_logger
from quart import Quart

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.metrics import get_http_metrics
from services.cj_assessment_service.protocols import CJRepositoryProtocol

logger = create_service_logger("cj_assessment_service.startup")


async def initialize_services(app: Quart, settings: Settings, container) -> None:
    """Initialize database schema and metrics (DI container already initialized in app.py)."""
    try:
        # Initialize database schema directly (following BOS/ELS pattern)
        async with container() as request_container:
            database = await request_container.get(CJRepositoryProtocol)
            await database.initialize_db_schema()
            logger.info("Database schema initialized successfully")

            # Get shared metrics (thread-safe singleton pattern)
            metrics = get_http_metrics()

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
