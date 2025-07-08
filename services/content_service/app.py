"""
HuleEdu Content Service Application.
"""

from __future__ import annotations

from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from huleedu_service_libs.metrics_middleware import setup_content_service_metrics_middleware
from quart import Quart
from quart_dishka import QuartDishka  # Added

from services.content_service import startup_setup
from services.content_service.api.content_routes import content_bp
from services.content_service.api.health_routes import health_bp
from services.content_service.config import settings
from services.content_service.startup_setup import create_di_container  # Added

# Configure structured logging
configure_service_logging("content-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("content.app")

app = Quart(__name__)

# Create DI container and setup QuartDishka integration before registering blueprints
_di_container = create_di_container()
QuartDishka(app=app, container=_di_container)


@app.before_serving
async def startup() -> None:
    """Initialize services and middleware."""
    try:
        await startup_setup.initialize_services(app, settings, _di_container)
        setup_content_service_metrics_middleware(app)
        logger.info("Content Service startup completed successfully")
    except Exception as e:
        logger.critical(f"Failed to start Content Service: {e}", exc_info=True)
        raise


@app.after_serving
async def shutdown() -> None:
    """Gracefully shutdown all services."""
    try:
        await startup_setup.shutdown_services()  # Uses global ref in startup_setup
        logger.info("Content Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during service shutdown: {e}", exc_info=True)


# Register Blueprints
app.register_blueprint(content_bp)
app.register_blueprint(health_bp)


if __name__ == "__main__":
    app.run(debug=settings.DEBUG, host=settings.HTTP_HOST, port=settings.HTTP_PORT)
