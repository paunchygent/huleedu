"""Health and metrics routes for File Service."""

from __future__ import annotations

from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from quart import Blueprint, Response, jsonify
from quart_dishka import inject

logger = create_service_logger("file_service.api.health")
health_bp = Blueprint("health_routes", __name__)


@health_bp.route("/healthz")
async def health_check() -> Response | tuple[Response, int]:
    """Standardized health check endpoint."""
    try:
        checks = {"service_responsive": True, "dependencies_available": True}
        dependencies = {}

        # File Service typically doesn't have complex dependencies
        # Add any filesystem or storage checks here as needed
        dependencies["storage"] = {
            "status": "healthy",
            "note": "Storage availability checked during file operations",
        }

        overall_status = "healthy"

        health_response = {
            "service": "file_service",
            "status": overall_status,
            "message": f"File Service is {overall_status}",
            "version": "1.0.0",
            "checks": checks,
            "dependencies": dependencies,
            "environment": "development",
        }

        return jsonify(health_response), 200

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify(
            {
                "service": "file_service",
                "status": "unhealthy",
                "message": "Health check failed",
                "version": "1.0.0",
                "error": str(e),
            }
        ), 503


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
