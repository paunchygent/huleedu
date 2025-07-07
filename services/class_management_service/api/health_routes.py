"""Health and metrics routes for Class Management Service."""

from __future__ import annotations

from dishka import FromDishka
from huleedu_service_libs.database import DatabaseHealthChecker
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from quart import Blueprint, Response, current_app, jsonify
from quart_dishka import inject

logger = create_service_logger("class_management_service.api.health")
health_bp = Blueprint("health_routes", __name__)


@health_bp.route("/healthz")
async def health_check() -> Response | tuple[Response, int]:
    """Standardized health check endpoint."""
    try:
        # Check database connectivity
        checks = {"service_responsive": True, "dependencies_available": True}
        dependencies = {}

        # Get database engine from app extensions
        engine = getattr(current_app, "database_engine", None)
        if engine:
            try:
                health_checker = DatabaseHealthChecker(engine, "class_management_service")
                summary = await health_checker.get_health_summary()
                dependencies["database"] = {"status": summary.get("status", "unknown")}
                if summary.get("status") not in ["healthy", "warning"]:
                    checks["dependencies_available"] = False
            except Exception as e:
                logger.warning(f"Database health check failed: {e}")
                dependencies["database"] = {"status": "unhealthy", "error": str(e)}
                checks["dependencies_available"] = False
        else:
            dependencies["database"] = {
                "status": "unknown",
                "note": "Database engine not configured",
            }

        overall_status = "healthy" if checks["dependencies_available"] else "unhealthy"

        health_response = {
            "service": "class_management_service",
            "status": overall_status,
            "message": f"Class Management Service is {overall_status}",
            "version": "1.0.0",
            "checks": checks,
            "dependencies": dependencies,
            "environment": "development",
        }

        status_code = 200 if overall_status == "healthy" else 503
        return jsonify(health_response), status_code

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify(
            {
                "service": "class_management_service",
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
