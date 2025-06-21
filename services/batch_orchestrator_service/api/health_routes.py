"""Health and metrics routes for Batch Orchestrator Service."""

from __future__ import annotations

from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from quart import Blueprint, Response, jsonify

logger = create_service_logger("bos.api.health")
health_bp = Blueprint("health_routes", __name__)


@health_bp.route("/healthz")
async def health_check() -> Response | tuple[Response, int]:
    """Health check endpoint."""
    return (
        jsonify(
            {
                "status": "ok",
                "message": "Batch Orchestrator Service is healthy",
            },
        ),
        200,
    )


@health_bp.route("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    try:
        metrics_data = generate_latest(REGISTRY)
        response = Response(metrics_data, content_type=CONTENT_TYPE_LATEST)
        return response
    except Exception as e:
        logger.error(f"Error generating metrics: {e}", exc_info=True)
        return Response("Error generating metrics", status=500)
