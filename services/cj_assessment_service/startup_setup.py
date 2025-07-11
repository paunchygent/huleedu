"""Startup and shutdown logic for CJ Assessment Service."""

from __future__ import annotations

from dishka import AsyncContainer
from huleedu_service_libs.database import DatabaseMetrics
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.quart_app import HuleEduApp

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.metrics import get_metrics

logger = create_service_logger("cj_assessment_service.startup")


async def initialize_services(
    app: HuleEduApp, settings: Settings, container: AsyncContainer
) -> None:
    """Initialize database schema using guaranteed infrastructure."""
    try:
        # Use guaranteed database engine for schema initialization
        async with app.database_engine.begin() as conn:
            from services.cj_assessment_service.models_db import Base

            await conn.run_sync(Base.metadata.create_all)

        logger.info("Database schema initialized successfully")

        # Initialize metrics with guaranteed infrastructure
        async with container() as request_container:
            database_metrics = await request_container.get(DatabaseMetrics)
            metrics = get_metrics(database_metrics)
            app.extensions["metrics"] = metrics

        logger.info("HTTP metrics initialized and stored in app extensions")
        logger.info(f"Available HTTP metrics: {list(metrics.keys())}")

        logger.info("CJ Assessment Service initialized successfully")
    except Exception as e:
        logger.critical(f"Failed to initialize CJ Assessment Service: {e}", exc_info=True)
        raise


async def shutdown_services() -> None:
    """Gracefully shutdown the service."""
    try:
        logger.info("CJ Assessment Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)
