"""
HuleEdu Batch Orchestrator Service Application.

This module implements the Batch Orchestrator Service REST API using Quart framework.
The service acts as the primary orchestrator for batch processing workflows.
"""

# Import Blueprints
# Import local modules using absolute imports for containerized deployment
import metrics
import startup_setup
from api.batch_routes import batch_bp
from api.health_routes import health_bp
from config import settings
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
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
        metrics.setup_metrics_middleware(app)
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
app.register_blueprint(health_bp)
