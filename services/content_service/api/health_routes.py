"""Health and metrics routes for Content Service."""

from __future__ import annotations

from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from quart import Blueprint, Response, jsonify
from quart_dishka import inject

from services.content_service.config import settings

logger = create_service_logger("content.api.health")
health_bp = Blueprint("health_routes", __name__)


@health_bp.route("/healthz")
async def health_check() -> Response | tuple[Response, int]:
    """Standardized health check endpoint with storage validation."""
    try:
        checks = {"service_responsive": True, "dependencies_available": True}
        dependencies = {}

        # Check storage accessibility
        try:
            store_path = settings.CONTENT_STORE_ROOT_PATH
            path_exists = store_path.exists()
            path_is_dir = store_path.is_dir()

            if not path_exists or not path_is_dir:
                logger.error(
                    f"Health check failed: Store root {store_path.resolve()} not accessible."
                )
                dependencies["storage"] = {
                    "status": "unhealthy",
                    "error": f"Storage path {store_path.resolve()} not accessible",
                    "path_exists": path_exists,
                    "path_is_dir": path_is_dir,
                }
                checks["dependencies_available"] = False
            else:
                dependencies["storage"] = {
                    "status": "healthy",
                    "path": str(store_path.resolve()),
                    "writable": True,  # Could add actual write test
                }
        except Exception as e:
            logger.error(f"Storage health check failed: {e}")
            dependencies["storage"] = {"status": "unhealthy", "error": str(e)}
            checks["dependencies_available"] = False

        overall_status = "healthy" if checks["dependencies_available"] else "unhealthy"

        health_response = {
            "service": "content_service",
            "status": overall_status,
            "message": f"Content Service is {overall_status}",
            "version": "1.0.0",
            "checks": checks,
            "dependencies": dependencies,
            "environment": "development",
        }

        status_code = 200 if overall_status == "healthy" else 503
        return jsonify(health_response), status_code

    except Exception as e:
        logger.error(f"Health check unexpected error: {e}", exc_info=True)
        return jsonify(
            {
                "service": "content_service",
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
