"""
HuleEdu Content Service Application.

This module implements the Content Service REST API using Quart framework.
It provides endpoints for uploading and downloading content with proper
error handling, logging, and health checks. Content is stored as files
on the local filesystem with UUID-based identifiers.
"""

from config import settings
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from prometheus_client import Counter, Histogram
from quart import Quart, Response, g, request

# Import Blueprints
from .api.content_routes import content_bp, set_content_dependencies
from .api.health_routes import health_bp, set_store_root

# Configure structured logging for the service
configure_service_logging("content-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("content.app")

# Prometheus metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

CONTENT_OPERATIONS = Counter(
    'content_operations_total',
    'Total content operations',
    ['operation', 'status']
)

# Determine store root from settings
STORE_ROOT = settings.CONTENT_STORE_ROOT_PATH

app = Quart(__name__)


@app.before_serving
async def startup() -> None:
    """Initialize the content store and share dependencies with Blueprints."""
    try:
        STORE_ROOT.mkdir(
            parents=True, exist_ok=True
        )  # await aiofiles.os.makedirs is not needed for pathlib
        logger.info(f"Content store root initialized at: {STORE_ROOT.resolve()}")

        # Share dependencies with Blueprint modules
        set_store_root(STORE_ROOT)
        set_content_dependencies(STORE_ROOT, CONTENT_OPERATIONS)

    except Exception as e:
        logger.critical(
            f"Failed to create storage directory {STORE_ROOT.resolve()}: {e}",
            exc_info=True,
        )
        # Consider if the app should exit if this fails.


@app.before_request
async def before_request() -> None:
    """Record request start time for duration metrics."""
    import time
    g.start_time = time.time()


@app.after_request
async def after_request(response: Response) -> Response:
    """Record metrics after each request."""
    try:
        import time
        start_time = getattr(g, 'start_time', None)
        if start_time is not None:
            duration = time.time() - start_time

            # Get endpoint name (remove query parameters)
            endpoint = request.path
            method = request.method
            status_code = str(response.status_code)

            # Record metrics
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
            REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

    except Exception as e:
        logger.error(f"Error recording request metrics: {e}")

    return response


# Register Blueprints
app.register_blueprint(content_bp)
app.register_blueprint(health_bp)


# Hypercorn config for Quart services
# PDM scripts will use these to run the app
# Example: pdm run start (uses hypercorn_config.py)
# Example: pdm run dev (uses quart run --debug)

if __name__ == "__main__":
    # For local dev, not for production container
    # Port is now sourced from settings
    app.run(host="0.0.0.0", port=settings.PORT, debug=True)
