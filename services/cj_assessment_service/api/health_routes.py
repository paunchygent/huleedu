"""Health and metrics routes for CJ Assessment Service.

This Blueprint provides the mandatory /healthz and /metrics endpoints
for operational monitoring and observability.
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from quart import Blueprint, Response, jsonify

health_bp = Blueprint('health_routes', __name__)


@health_bp.route("/healthz")
async def health_check() -> Response:
    """Health check endpoint for CJ Assessment Service.

    Performs basic service responsiveness check. Can be extended
    to validate database and Kafka connectivity via DI.

    Returns:
        JSON response with service health status
    """
    # Basic service health check
    # TODO: Add DB/Kafka connectivity checks via injected dependencies

    health_status = {
        "status": "ok",
        "message": "CJ Assessment Service is healthy",
        "service": "cj_assessment_service",
        "checks": {
            "service_responsive": True,
            # "database_connected": True,  # TODO: Add with DI
            # "kafka_connected": True,     # TODO: Add with DI
        }
    }

    return jsonify(health_status), 200


@health_bp.route("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint.

    Serves metrics in OpenMetrics format for Prometheus scraping.

    Returns:
        Prometheus-formatted metrics data
    """
    try:
        metrics_data = generate_latest()
        return Response(metrics_data, content_type=CONTENT_TYPE_LATEST)
    except Exception:
        # Return error response but don't crash the service
        error_response = (
            "# HELP metrics_error Metrics generation failed\n"
            "# TYPE metrics_error gauge\nmetrics_error 1\n"
        )
        return Response(
            error_response, content_type=CONTENT_TYPE_LATEST, status=500
        )
