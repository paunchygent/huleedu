"""Entitlements Service Application.

This module provides the main Quart application for the Entitlements Service,
managing credit systems, rate limiting, and usage tracking for LLM operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dishka import make_async_container
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.error_handling.quart import create_error_response
from huleedu_service_libs.logging_utils import (
    configure_service_logging,
    create_service_logger,
)
from huleedu_service_libs.metrics_middleware import (
    setup_standard_service_metrics_middleware,
)
from huleedu_service_libs.middleware.frameworks.quart_correlation_middleware import (
    setup_correlation_middleware,
)
from huleedu_service_libs.middleware.frameworks.quart_middleware import (
    setup_tracing_middleware,
)
from huleedu_service_libs.observability import init_tracing
from huleedu_service_libs.outbox import OutboxProvider
from huleedu_service_libs.quart_app import HuleEduApp
from pydantic import ValidationError
from quart_dishka import QuartDishka
from sqlalchemy.ext.asyncio import create_async_engine

from services.entitlements_service.config import Settings
from services.entitlements_service.di import (
    CoreProvider,
    EntitlementsServiceProvider,
    ImplementationProvider,
    ServiceProvider,
)
from services.entitlements_service.startup_setup import initialize_services, shutdown_services

if TYPE_CHECKING:
    from quart import Response

logger = create_service_logger("entitlements_service")


def create_app(settings: Settings | None = None) -> HuleEduApp:
    """Create and configure the Quart application.

    Args:
        settings: Optional settings override for testing

    Returns:
        Configured Quart application with integrated lifecycle
    """
    if settings is None:
        settings = Settings()

    # Configure logging
    configure_service_logging("entitlements_service", log_level=settings.LOG_LEVEL)

    # Create HuleEduApp with guaranteed infrastructure
    app = HuleEduApp(__name__)

    # Configure app settings
    app.config.update(
        {
            "TESTING": False,
            "DEBUG": settings.LOG_LEVEL == "DEBUG",
        }
    )

    # Initialize guaranteed infrastructure immediately
    app.database_engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_pre_ping=settings.DATABASE_POOL_PRE_PING,
        pool_recycle=settings.DATABASE_POOL_RECYCLE,
    )
    app.container = make_async_container(
        CoreProvider(),
        ImplementationProvider(),
        ServiceProvider(),
        EntitlementsServiceProvider(engine=app.database_engine),
        # Add OutboxProvider for transactional outbox pattern
        OutboxProvider(),
    )
    app.extensions = {}

    # Optional service-specific attributes
    app.consumer_task = None
    app.consumer_monitor_task = None
    app._consumer_shutdown_requested = False
    app.kafka_consumer = None
    app.relay_worker = None

    # Setup dependency injection
    QuartDishka(app=app, container=app.container)

    # Initialize tracing early, before blueprint registration
    tracer = init_tracing("entitlements_service")
    app.extensions["tracer"] = tracer
    setup_tracing_middleware(app, tracer)
    # Correlation context middleware (must run early in request lifecycle)
    setup_correlation_middleware(app)

    # Register health Blueprint
    from services.entitlements_service.api.health_routes import health_bp

    app.register_blueprint(health_bp)

    # Register entitlements API Blueprint
    from services.entitlements_service.api.entitlements_routes import entitlements_bp

    app.register_blueprint(entitlements_bp, url_prefix="/v1/entitlements")

    # Register admin API Blueprint (dev/admin only)
    if not settings.is_production():
        from services.entitlements_service.api.admin_routes import admin_bp

        app.register_blueprint(admin_bp, url_prefix="/v1/admin")

    @app.before_serving
    async def startup() -> None:
        """Application startup tasks."""
        try:
            # Initialize services using guaranteed infrastructure
            await initialize_services(app, settings, app.container)

            # Setup metrics middleware
            setup_standard_service_metrics_middleware(app, "entitlements")

            # Kafka consumer is started in startup_setup.initialize_services

            logger.info("Entitlements Service started successfully")
            logger.info("Health endpoint: /healthz")
            logger.info("Metrics endpoint: /metrics")
            logger.info(f"API endpoints: /v1/entitlements/* on port {settings.HTTP_PORT}")
            if not settings.is_production():
                logger.info("Admin endpoints: /v1/admin/* (development mode)")

        except Exception as e:
            logger.critical(f"Failed to start Entitlements Service: {e}", exc_info=True)
            raise

    @app.after_serving
    async def cleanup() -> None:
        """Application cleanup tasks."""
        try:
            # Stop EventRelayWorker if configured
            if app.relay_worker:
                logger.info("Stopping EventRelayWorker...")
                await app.relay_worker.stop()
                logger.info("EventRelayWorker stopped")

            # Signal monitor to stop
            app._consumer_shutdown_requested = True

            # Stop Kafka consumer if configured
            if app.kafka_consumer:
                logger.info("Stopping Kafka consumer...")
                await app.kafka_consumer.stop_consumer()
            if app.consumer_task and not app.consumer_task.done():
                logger.info("Cancelling Kafka consumer task...")
                app.consumer_task.cancel()
                try:
                    await app.consumer_task
                except Exception:
                    pass
            # Stop monitor task
            if app.consumer_monitor_task and not app.consumer_monitor_task.done():
                logger.info("Cancelling Kafka consumer monitor task...")
                app.consumer_monitor_task.cancel()
                try:
                    await app.consumer_monitor_task
                except Exception:
                    pass

            # Additional cleanup
            await shutdown_services()

            logger.info("Entitlements Service shutdown complete")

        except Exception as e:
            logger.error(f"Error during shutdown: {e}", exc_info=True)

    @app.errorhandler(HuleEduError)
    async def handle_huleedu_error(error: HuleEduError) -> tuple[Response, int]:
        """Handle HuleEdu business errors."""
        logger.warning(f"Business error: {error.error_detail.message}")
        return create_error_response(error.error_detail)

    @app.errorhandler(ValidationError)
    async def handle_validation_error(error: ValidationError) -> tuple[dict[str, Any], int]:
        """Handle Pydantic validation errors."""
        logger.warning(f"Validation error: {error}")
        return {
            "error": "validation_error",
            "message": "Invalid request data",
            "details": error.errors(),
            "service": "entitlements_service",
        }, 400

    @app.errorhandler(Exception)
    async def handle_exception(e: Exception) -> tuple[dict[str, Any], int]:
        """Global exception handler for API errors."""
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        return {
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "service": "entitlements_service",
        }, 500

    return app


# Create app instance
app = create_app()

# Development configuration
if __name__ == "__main__":
    settings = Settings()
    config = {
        "bind": f"0.0.0.0:{settings.HTTP_PORT}",
        "workers": 1,
        "worker_class": "quart.serving.asyncio.ASGIWorker",
        "accesslog": "-",
        "errorlog": "-",
        "loglevel": settings.LOG_LEVEL.lower(),
    }
    logger.info(f"Starting Entitlements Service on port {settings.HTTP_PORT}")
    import sys

    sys.exit("Please use 'pdm run dev' or 'docker compose up' to start the service")
