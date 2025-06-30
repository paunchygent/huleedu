"""
HuleEdu Batch Orchestrator Service Application.

This module implements the Batch Orchestrator Service REST API using Quart framework.
The service acts as the primary orchestrator for batch processing workflows.
"""

from __future__ import annotations

# Import Blueprints
# Import local modules using absolute imports for containerized deployment
from services.batch_orchestrator_service import startup_setup
from services.batch_orchestrator_service.api.batch_routes import batch_bp, internal_bp
from services.batch_orchestrator_service.api.health_routes import health_bp
from services.batch_orchestrator_service.config import settings
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from huleedu_service_libs.metrics_middleware import setup_standard_service_metrics_middleware
from quart import Quart

# Configure structured logging for the service
configure_service_logging("batch-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("bos.app")

app = Quart(__name__)


@app.before_serving
async def startup() -> None:
    """Initialize services and middleware."""
    try:
        await startup_setup.initialize_services(app, settings)
        setup_standard_service_metrics_middleware(app, "bos")
        logger.info("Batch Orchestrator Service startup completed successfully")
    except Exception as e:
        logger.critical(f"Failed to start Batch Orchestrator Service: {e}", exc_info=True)
        raise


@app.after_serving
async def shutdown() -> None:
    """Gracefully shutdown all services."""
    try:
        await startup_setup.shutdown_services()
        logger.info("Batch Orchestrator Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during service shutdown: {e}", exc_info=True)


# Register Blueprints
app.register_blueprint(batch_bp)
app.register_blueprint(internal_bp)  # Internal API for Result Aggregator Service
app.register_blueprint(health_bp)


if __name__ == "__main__":
    import asyncio

    import hypercorn.asyncio
    from hypercorn import Config

    # Create hypercorn config with our settings
    config = Config()
    config.bind = [f"{settings.HOST}:{settings.PORT}"]
    config.workers = settings.WEB_CONCURRENCY
    config.worker_class = "asyncio"
    config.loglevel = settings.LOG_LEVEL.lower()
    config.graceful_timeout = settings.GRACEFUL_TIMEOUT
    config.keep_alive_timeout = settings.KEEP_ALIVE_TIMEOUT

    asyncio.run(hypercorn.asyncio.serve(app, config))
