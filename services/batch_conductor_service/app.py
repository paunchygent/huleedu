"""
HuleEdu Batch Conductor Service Application.

This module implements the Batch Conductor Service internal HTTP API using Quart framework.
The service provides pipeline dependency resolution and batch state analysis for BOS.
"""

from __future__ import annotations

from quart import Quart
from quart_dishka import QuartDishka

from huleedu_service_libs.logging_utils import (
    configure_service_logging,
    create_service_logger,
)
from huleedu_service_libs.metrics_middleware import setup_metrics_middleware
from services.batch_conductor_service.api.health_routes import health_bp
from services.batch_conductor_service.api.pipeline_routes import pipeline_bp
from services.batch_conductor_service.config import settings
from services.batch_conductor_service.startup_setup import (
    create_container,
    initialize_metrics,
    shutdown_services,
)

# Configure structured logging for the service
configure_service_logging("batch-conductor-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("bcs.app")

app = Quart(__name__)

# --- Dependency Injection (must be wired before blueprint registration) ---
container = create_container()
QuartDishka(app=app, container=container)


@app.before_serving
async def startup() -> None:
    """Initialize middleware and metrics."""
    try:
        # Metrics rely on the DI container which is already wired
        await initialize_metrics(app, container)
        setup_metrics_middleware(
            app,
            request_count_metric_name="http_requests_total",
            request_duration_metric_name="http_request_duration_seconds",
            status_label_name="status_code",
            logger_name="bcs.metrics",
        )
        logger.info("Batch Conductor Service startup completed successfully")
    except Exception as e:
        logger.critical("Failed to start Batch Conductor Service: %s", e, exc_info=True)
        raise


@app.after_serving
async def shutdown() -> None:
    """Gracefully shutdown all services."""
    try:
        await shutdown_services()
        logger.info("Batch Conductor Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during service shutdown: {e}", exc_info=True)


# Register Blueprints
app.register_blueprint(health_bp)
app.register_blueprint(pipeline_bp)


if __name__ == "__main__":
    import asyncio

    import hypercorn.asyncio
    from hypercorn import Config

    # Create hypercorn config with our settings
    config = Config()
    config.bind = [f"{settings.HTTP_HOST}:{settings.HTTP_PORT}"]
    config.worker_class = "asyncio"
    config.loglevel = settings.LOG_LEVEL.lower()
    config.graceful_timeout = 30
    config.keep_alive_timeout = 60

    asyncio.run(hypercorn.asyncio.serve(app, config))
