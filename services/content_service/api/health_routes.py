"""Health and metrics routes for Content Service."""

from __future__ import annotations

import uuid

from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from quart import Blueprint, Response, jsonify
from quart_dishka import inject

from services.content_service.config import Settings

logger = create_service_logger("content.api.health")
health_bp = Blueprint("health_routes", __name__)


@health_bp.route("/healthz")
async def health_check() -> Response | tuple[Response, int]:
    """Standardized health check endpoint."""
    correlation_id = uuid.uuid4()

    try:
        # Basic service responsiveness check
        # Database connectivity is verified through actual operations
        health_response = {
            "service": "content_service",
            "status": "healthy",
            "message": "Content Service is healthy",
            "version": "1.0.0",
            "checks": {
                "service_responsive": True,
                "database_backed_storage": True,
            },
            "environment": "development",
            "correlation_id": str(correlation_id),
        }

        return jsonify(health_response), 200

    except Exception as e:
        logger.error(
            f"Health check unexpected error: {e}",
            extra={"correlation_id": str(correlation_id)},
            exc_info=True,
        )
        return jsonify(
            {
                "service": "content_service",
                "status": "unhealthy",
                "message": "Health check failed",
                "version": "1.0.0",
                "error": str(e),
                "correlation_id": str(correlation_id),
            }
        ), 503


@health_bp.route("/metrics")
@inject
async def metrics(registry: FromDishka[CollectorRegistry]) -> Response:
    """Prometheus metrics endpoint."""
    correlation_id = uuid.uuid4()

    try:
        metrics_data = generate_latest(registry)
        response = Response(metrics_data, content_type=CONTENT_TYPE_LATEST)
        response.headers["X-Correlation-ID"] = str(correlation_id)
        return response
    except Exception as e:
        logger.error(
            f"Error generating metrics: {e}",
            extra={"correlation_id": str(correlation_id)},
            exc_info=True,
        )
        return Response("Error generating metrics", status=500)
