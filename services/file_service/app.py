"""
HuleEdu File Service Application.

This module implements the File Service HTTP API using Quart framework.
The service handles file uploads, text extraction, and event publishing.
"""

from __future__ import annotations

# Import local modules using relative imports for containerized deployment
from api.file_routes import file_bp
from api.health_routes import health_bp
from config import settings
from di import FileServiceProvider
from dishka import make_async_container
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from prometheus_client import Counter, Histogram
from quart import Quart, Response, request
from quart_dishka import QuartDishka

# Configure structured logging for the service
configure_service_logging("file-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("file_service.app")

app = Quart(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter(
    "file_service_requests_total", "Total number of HTTP requests", ["method", "endpoint", "status"]
)

REQUEST_DURATION = Histogram(
    "file_service_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)


@app.before_serving
async def startup() -> None:
    """Initialize services and middleware."""
    try:
        # Setup Dishka DI container
        container = make_async_container(FileServiceProvider())
        QuartDishka(app=app, container=container)

        logger.info("File Service startup completed successfully")
    except Exception as e:
        logger.critical(f"Failed to start File Service: {e}", exc_info=True)
        raise


@app.after_serving
async def shutdown() -> None:
    """Gracefully shutdown all services."""
    try:
        # Close any async resources if needed
        logger.info("File Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during service shutdown: {e}", exc_info=True)


@app.before_request
async def before_request() -> None:
    """Record request start time for duration metrics."""
    import time

    from quart import g

    g.start_time = time.time()


@app.after_request
async def after_request(response: Response) -> Response:
    """Record metrics after each request."""
    try:
        import time

        from quart import g

        start_time = getattr(g, "start_time", None)
        if start_time is not None:
            duration = time.time() - start_time

            # Get endpoint name and method
            endpoint = request.path
            method = request.method
            status_code = str(response.status_code)

            # Record metrics
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status_code).inc()
            REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

    except Exception as e:
        logger.error(f"Error recording request metrics: {e}")

    return response


# Register Blueprints
app.register_blueprint(file_bp)
app.register_blueprint(health_bp)
