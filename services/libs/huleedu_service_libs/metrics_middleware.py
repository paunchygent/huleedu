"""Shared Prometheus metrics middleware for HuleEdu HTTP services.

This module provides a common metrics middleware implementation that can be
configured for different service-specific metric naming conventions.
"""

from __future__ import annotations

import time

from huleedu_service_libs.logging_utils import create_service_logger
from quart import Quart, Response, current_app, g, request

logger = create_service_logger("huleedu.metrics_middleware")


def setup_metrics_middleware(
    app: Quart,
    request_count_metric_name: str = "request_count",
    request_duration_metric_name: str = "request_duration",
    status_label_name: str = "status_code",
    logger_name: str | None = None,
) -> None:
    """Setup Prometheus metrics middleware for a Quart application.

    This function sets up HTTP request/response middleware to automatically
    record metrics for all requests processed by the application.

    Args:
        app: The Quart application to configure
        request_count_metric_name: Name of the request counter metric
            (e.g., "request_count" or "http_requests_total")
        request_duration_metric_name: Name of the request duration metric
            (e.g., "request_duration" or "http_request_duration_seconds")
        status_label_name: Name of the status code label
            (e.g., "status_code" or "status")
        logger_name: Optional custom logger name for this service

    Note:
        The metrics instances must be stored in app.extensions["metrics"] as a dict
        containing the metric objects. This is typically done in startup_setup.py
        using the _create_metrics() function pattern.
    """
    # Create service-specific logger if provided
    service_logger = create_service_logger(logger_name) if logger_name else logger

    @app.before_request
    async def before_request() -> None:
        """Record request start time for duration metrics."""
        g.start_time = time.time()

    @app.after_request
    async def after_request(response: Response) -> Response:
        """Record metrics after each request."""
        try:
            start_time = getattr(g, "start_time", None)

            # Access metrics through proper app context (supporting both patterns)
            extensions = getattr(current_app, "extensions", {})
            metrics = extensions.get("metrics", {}) if extensions else {}

            if start_time is not None and metrics:
                duration = time.time() - start_time

                # Get endpoint name (remove query parameters)
                endpoint = request.path
                method = request.method
                status_code = str(response.status_code)

                # Record metrics using configurable metric names
                request_count = metrics.get(request_count_metric_name)
                request_duration = metrics.get(request_duration_metric_name)

                if request_count:
                    request_count.labels(
                        method=method,
                        endpoint=endpoint,
                        **{status_label_name: status_code},
                    ).inc()
                if request_duration:
                    request_duration.labels(method=method, endpoint=endpoint).observe(duration)

        except Exception as e:
            service_logger.error(f"Error recording request metrics: {e}")

        return response


def setup_content_service_metrics_middleware(app: Quart) -> None:
    """Setup metrics middleware with Content Service naming conventions.

    Uses:
    - http_requests_total (request count)
    - http_request_duration_seconds (request duration)
    - status_code (status label)
    """
    setup_metrics_middleware(
        app=app,
        request_count_metric_name="http_requests_total",
        request_duration_metric_name="http_request_duration_seconds",
        status_label_name="status_code",
        logger_name="content.metrics",
    )


def setup_standard_service_metrics_middleware(app: Quart, service_name: str) -> None:
    """Setup metrics middleware with standard HuleEdu naming conventions.

    Uses:
    - request_count (request count)
    - request_duration (request duration)
    - status_code (status label)

    Args:
        app: The Quart application to configure
        service_name: Service name for logger (e.g., "bos", "els", "file_service")
    """
    setup_metrics_middleware(
        app=app,
        request_count_metric_name="request_count",
        request_duration_metric_name="request_duration",
        status_label_name="status_code",
        logger_name=f"{service_name}.metrics",
    )


def setup_file_service_metrics_middleware(app: Quart) -> None:
    """Setup metrics middleware with File Service naming conventions.

    Uses:
    - request_count (request count)
    - request_duration (request duration)
    - status (status label - different from others!)
    """
    setup_metrics_middleware(
        app=app,
        request_count_metric_name="request_count",
        request_duration_metric_name="request_duration",
        status_label_name="status",  # File service uses "status" instead of "status_code"
        logger_name="file_service.metrics",
    )
