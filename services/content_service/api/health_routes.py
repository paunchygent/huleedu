"""Health and metrics routes for Content Service."""

from typing import Union

from config import settings
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from quart import Blueprint, Response, jsonify

logger = create_service_logger("content.api.health")
health_bp = Blueprint("health_routes", __name__)


@health_bp.route("/healthz")
async def health_check() -> Union[Response, tuple[Response, int]]:
    """Health check endpoint."""
    try:
        store_path = settings.CONTENT_STORE_ROOT_PATH
        path_exists = store_path.exists()
        path_is_dir = store_path.is_dir()
        if not path_exists or not path_is_dir:
            logger.error(f"Health check failed: Store root {store_path.resolve()} not accessible.")
            return (
                jsonify({"status": "unhealthy", "message": "Storage not accessible"}),
                503,
            )
        return jsonify({"status": "ok", "message": "Content Service is healthy."}), 200
    except Exception as e:
        logger.error(f"Health check unexpected error: {e}", exc_info=True)
        return jsonify({"status": "unhealthy", "message": "Health check error"}), 500


@health_bp.route("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    try:
        metrics_data = generate_latest()
        response = Response(metrics_data, content_type=CONTENT_TYPE_LATEST)
        return response
    except Exception as e:
        logger.error(f"Error generating metrics: {e}", exc_info=True)
        return Response("Error generating metrics", status=500)
