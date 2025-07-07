"""Health and metrics routes for CJ Assessment Service.

This Blueprint provides the mandatory /healthz and /metrics endpoints
for operational monitoring and observability.
"""

from __future__ import annotations

from dishka import FromDishka
from huleedu_service_libs.database import DatabaseHealthChecker
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry
from quart import Blueprint, Response, current_app, jsonify
from quart_dishka import inject

health_bp = Blueprint("health_routes", __name__)


@health_bp.route("/healthz")
async def health_check() -> tuple[Response, int]:
    """Standardized health check endpoint for CJ Assessment Service."""
    try:
        # Check database connectivity
        checks = {"service_responsive": True, "dependencies_available": True}
        dependencies = {}

        # Get database engine from app extensions
        engine = getattr(current_app, "database_engine", None)
        if engine:
            try:
                health_checker = DatabaseHealthChecker(engine, "cj_assessment_service")
                summary = await health_checker.get_health_summary()
                dependencies["database"] = {"status": summary.get("status", "unknown")}
                if summary.get("status") not in ["healthy", "warning"]:
                    checks["dependencies_available"] = False
            except Exception as e:
                from huleedu_service_libs.logging_utils import create_service_logger

                logger = create_service_logger("cj_assessment_service.api.health")
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
            "service": "cj_assessment_service",
            "status": overall_status,
            "message": f"CJ Assessment Service is {overall_status}",
            "version": "1.0.0",
            "checks": checks,
            "dependencies": dependencies,
            "environment": "development",
        }

        status_code = 200 if overall_status == "healthy" else 503
        return jsonify(health_response), status_code

    except Exception as e:
        from huleedu_service_libs.logging_utils import create_service_logger

        logger = create_service_logger("cj_assessment_service.api.health")
        logger.error(f"Health check failed: {e}")
        return jsonify(
            {
                "service": "cj_assessment_service",
                "status": "unhealthy",
                "message": "Health check failed",
                "version": "1.0.0",
                "error": str(e),
            }
        ), 503


@health_bp.route("/healthz/database")
async def database_health_check() -> Response | tuple[Response, int]:
    """Database-specific health check endpoint with detailed metrics."""
    try:
        # Get database engine from app extensions or container
        engine = getattr(current_app, "database_engine", None)
        if not engine:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Database engine not configured",
                        "timestamp": None,
                    }
                ),
                503,
            )

        # Create health checker and perform comprehensive check
        health_checker = DatabaseHealthChecker(engine, "cj_assessment_service")
        health_result = await health_checker.comprehensive_health_check()

        # Determine HTTP status code based on health status
        status_code = 200
        if health_result.get("overall_status") in ["unhealthy", "error"]:
            status_code = 503
        elif health_result.get("overall_status") == "warning":
            status_code = 200  # Warning is still considered healthy for load balancer

        return (jsonify(health_result), status_code)

    except Exception as e:
        from huleedu_service_libs.logging_utils import create_service_logger

        logger = create_service_logger("cj_assessment_service.api.health")
        logger.error(f"Database health check failed: {e}", exc_info=True)
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Health check failed: {str(e)}",
                    "service": "cj_assessment_service",
                    "timestamp": None,
                }
            ),
            503,
        )


@health_bp.route("/healthz/database/summary")
async def database_health_summary() -> Response | tuple[Response, int]:
    """Lightweight database health summary for frequent polling."""
    try:
        # Get database engine from app extensions or container
        engine = getattr(current_app, "database_engine", None)
        if not engine:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Database engine not configured",
                    }
                ),
                503,
            )

        # Create health checker and get summary
        health_checker = DatabaseHealthChecker(engine, "cj_assessment_service")
        summary = await health_checker.get_health_summary()

        # Determine HTTP status code
        status_code = 200 if summary.get("status") in ["healthy", "warning"] else 503

        return (jsonify(summary), status_code)

    except Exception as e:
        from huleedu_service_libs.logging_utils import create_service_logger

        logger = create_service_logger("cj_assessment_service.api.health")
        logger.error(f"Database health summary failed: {e}", exc_info=True)
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Health summary failed: {str(e)}",
                    "service": "cj_assessment_service",
                }
            ),
            503,
        )


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
