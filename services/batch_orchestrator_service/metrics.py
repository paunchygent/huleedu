"""Prometheus metrics setup and middleware for Batch Orchestrator Service."""

from __future__ import annotations

import time

from huleedu_service_libs.logging_utils import create_service_logger
from quart import Quart, Response, current_app, g, request

logger = create_service_logger("bos.metrics")


def setup_metrics_middleware(app: Quart) -> None:
    """Setup Prometheus metrics middleware for the Quart app."""

    @app.before_request
    async def before_request() -> None:
        """Record request start time for duration metrics."""
        g.start_time = time.time()

    @app.after_request
    async def after_request(response: Response) -> Response:
        """Record metrics after each request."""
        try:
            start_time = getattr(g, "start_time", None)

            # Access metrics through proper app context (following Quart patterns)
            extensions = getattr(current_app, 'extensions', {})
            metrics = extensions.get('metrics', {}) if extensions else {}

            if start_time is not None and metrics:
                duration = time.time() - start_time

                # Get endpoint name (remove query parameters)
                endpoint = request.path
                method = request.method
                status_code = str(response.status_code)

                # Record metrics
                request_count = metrics.get('request_count')
                request_duration = metrics.get('request_duration')

                if request_count:
                    request_count.labels(
                        method=method, endpoint=endpoint, status_code=status_code
                    ).inc()
                if request_duration:
                    request_duration.labels(method=method, endpoint=endpoint).observe(duration)

        except Exception as e:
            logger.error(f"Error recording request metrics: {e}")

        return response
