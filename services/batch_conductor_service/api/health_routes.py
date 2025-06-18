"""Health and metrics routes for Batch Conductor Service."""

from __future__ import annotations

from dishka import FromDishka
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from quart import Blueprint, Response, jsonify
from quart_dishka import inject

from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("bcs.api.health")
health_bp = Blueprint("health_routes", __name__)


@health_bp.route("/healthz")
async def health_check() -> Response | tuple[Response, int]:
    """Health check endpoint."""
    return (
        jsonify(
            {
                "status": "ok",
                "message": "Batch Conductor Service is healthy",
            }
        ),
        200,
    )


@health_bp.route("/metrics")
@inject
async def metrics(registry: FromDishka[CollectorRegistry]) -> Response:
    """Prometheus metrics endpoint."""
    try:
        metrics_data = generate_latest(registry)
        response = Response(metrics_data, content_type=CONTENT_TYPE_LATEST)
        return response
    except Exception as e:
        logger.error(f"Error generating metrics: {e}", exc_info=True)
        return Response("Error generating metrics", status=500)
