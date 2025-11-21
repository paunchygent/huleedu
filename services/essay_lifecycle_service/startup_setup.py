"""Startup and shutdown logic for Essay Lifecycle Service API."""

from __future__ import annotations

from common_core.status_enums import EssayStatus
from dishka import make_async_container
from huleedu_service_libs.database import DatabaseMetrics
from huleedu_service_libs.database.enum_validation import EnumDriftError, assert_enum_contains
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.outbox import OutboxProvider
from huleedu_service_libs.quart_app import HuleEduApp
from quart_dishka import QuartDishka
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.di import (
    BatchCoordinationProvider,
    CommandHandlerProvider,
    CoreInfrastructureProvider,
    ServiceClientsProvider,
)
from services.essay_lifecycle_service.implementations.essay_repository_postgres_impl import (
    PostgreSQLEssayRepository,
)
from services.essay_lifecycle_service.metrics import get_http_metrics
from services.essay_lifecycle_service.models_db import Base

# Global references for service management (unavoidable for Quart lifecycle)
# ELS doesn't need background tasks like BOS, but keeping structure consistent


async def initialize_services(app: HuleEduApp, settings: Settings) -> None:
    """Initialize DI container, Quart-Dishka integration, and metrics."""
    logger = create_service_logger("els.startup")

    try:
        # Initialize DI container with all provider classes
        container = make_async_container(
            CoreInfrastructureProvider(),
            ServiceClientsProvider(),
            CommandHandlerProvider(),
            BatchCoordinationProvider(),
            OutboxProvider(),
        )
        QuartDishka(app=app, container=container)

        # Get database metrics from container for integration
        async with container() as request_container:
            database_metrics = await request_container.get(DatabaseMetrics)

        # Initialize metrics using shared module with database metrics and store in app context
        metrics = get_http_metrics()
        # Update metrics with database metrics
        from services.essay_lifecycle_service.metrics import get_metrics

        metrics = get_metrics(database_metrics)

        # Store metrics in app context (proper Quart pattern)
        app.extensions = getattr(app, "extensions", {})
        app.extensions["metrics"] = metrics

        # Initialize database schema and store engine for health checks (production only)
        if settings.ENVIRONMENT != "testing" and not getattr(
            settings, "USE_MOCK_REPOSITORY", False
        ):
            # Create engine and session factory for schema initialization
            engine = create_async_engine(settings.DATABASE_URL, echo=False)
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            # Create temporary repository instance with session factory
            PostgreSQLEssayRepository(session_factory)
            app.database_engine = engine
            logger.info("Database schema initialized and engine stored for health checks")

            # Fail-fast enum validation in non-production environments
            if settings.ENVIRONMENT != "production":
                try:
                    await assert_enum_contains(
                        engine,
                        "essay_status_enum",
                        (status.value for status in EssayStatus),
                        service_name="essay_lifecycle_service",
                    )
                    logger.info("Enum validation passed for essay_status_enum")
                except EnumDriftError:
                    logger.critical("Enum validation failed for essay_status_enum", exc_info=True)
                    raise

        logger.info(
            "Essay Lifecycle Service DI container, quart-dishka integration, "
            "and metrics initialized successfully."
        )
    except Exception as e:
        logger.critical(f"Failed to initialize Essay Lifecycle Service: {e}", exc_info=True)
        raise


async def shutdown_services() -> None:
    """Gracefully shutdown services."""
    logger = create_service_logger("els.startup")

    try:
        # ELS API doesn't have background tasks to shutdown like BOS
        # But keeping structure consistent for future needs
        logger.info("Essay Lifecycle Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)
