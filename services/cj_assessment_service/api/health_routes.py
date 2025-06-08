"""Health and metrics routes for CJ Assessment Service.

This Blueprint provides the mandatory /healthz and /metrics endpoints
for operational monitoring and observability.
"""

from __future__ import annotations

from dishka import FromDishka
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry
from quart import Blueprint, Response, jsonify
from quart_dishka import inject

health_bp = Blueprint('health_routes', __name__)


@health_bp.route("/healthz")
async def health_check():
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
@inject
async def metrics(registry: FromDishka[CollectorRegistry]) -> Response:
    """Prometheus metrics endpoint.

    Serves metrics in OpenMetrics format for Prometheus scraping.

    Returns:
        Prometheus-formatted metrics data
    """
    try:
        from prometheus_client import generate_latest
        metrics_data = generate_latest(registry)
        return Response(metrics_data, content_type=CONTENT_TYPE_LATEST)
    except Exception as e:
        from huleedu_service_libs.logging_utils import create_service_logger
        logger = create_service_logger("cj_assessment_service.api.health")
        logger.error(f"Error generating metrics: {e}", exc_info=True)
        return Response("Error generating metrics", status=500)
