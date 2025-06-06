"""
HuleEdu Content Service Application.
"""

from __future__ import annotations

import metrics
import startup_setup
from api.content_routes import content_bp
from api.health_routes import health_bp
from config import settings
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from quart import Quart

# Configure structured logging
configure_service_logging("content-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("content.app")

app = Quart(__name__)


@app.before_serving
async def startup() -> None:
    """Initialize services and middleware."""
    try:
        await startup_setup.initialize_services(app, settings)
        metrics.setup_metrics_middleware(app)
        logger.info("Content Service startup completed successfully")
    except Exception as e:
        logger.critical(f"Failed to start Content Service: {e}", exc_info=True)
        raise


@app.after_serving
async def shutdown() -> None:
    """Gracefully shutdown all services."""
    try:
        await startup_setup.shutdown_services()
        logger.info("Content Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during service shutdown: {e}", exc_info=True)


# Register Blueprints
app.register_blueprint(content_bp)
app.register_blueprint(health_bp)


if __name__ == "__main__":
    import asyncio

    import hypercorn.asyncio
    from hypercorn import Config

    # Explicit hypercorn configuration
    config = Config()
    config.bind = [f"{settings.HOST}:{settings.PORT}"]
    config.workers = settings.WEB_CONCURRENCY
    config.worker_class = "asyncio"
    config.loglevel = settings.LOG_LEVEL.lower()

    asyncio.run(hypercorn.asyncio.serve(app, config))
