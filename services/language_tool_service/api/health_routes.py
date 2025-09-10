"""Health and metrics routes for Language Tool Service."""

from __future__ import annotations

from dishka import FromDishka
from huleedu_service_libs.error_handling.correlation import CorrelationContext
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from quart import Blueprint, Response, jsonify
from quart_dishka import inject

from services.language_tool_service.config import Settings
from services.language_tool_service.protocols import (
    LanguageToolManagerProtocol,
    LanguageToolWrapperProtocol,
)

logger = create_service_logger("language_tool_service.api.health")
health_bp = Blueprint("health_routes", __name__)


@health_bp.route("/healthz")
@inject
async def health_check(
    settings: FromDishka[Settings],
    corr: FromDishka[CorrelationContext],
    language_tool_wrapper: FromDishka[LanguageToolWrapperProtocol],
    language_tool_manager: FromDishka[LanguageToolManagerProtocol],
) -> Response | tuple[Response, int]:
    """Standardized health check endpoint with dependency status."""
    try:
        checks = {"service_responsive": True, "dependencies_available": True}
        dependencies = {}

        # Check Language Tool wrapper health
        try:
            wrapper_health = await language_tool_wrapper.get_health_status(corr)
            dependencies["language_tool_wrapper"] = {
                "status": "healthy",
                **wrapper_health,
            }
        except Exception as e:
            logger.warning(
                f"Language Tool wrapper health check failed: {e}",
                correlation_id=corr.original,
            )
            dependencies["language_tool_wrapper"] = {
                "status": "unhealthy",
                "error": str(e),
            }
            checks["dependencies_available"] = False

        overall_status = "healthy" if all(checks.values()) else "degraded"

        # Get JVM status (TASK-052G requirement)
        jvm_running = False
        heap_used_mb = 0

        if (
            "language_tool_wrapper" in dependencies
            and dependencies["language_tool_wrapper"]["status"] == "healthy"
        ):
            server_info = dependencies["language_tool_wrapper"].get("server", {})
            jvm_running = server_info.get("running", False)

            # Get actual heap usage if JVM is running
            if jvm_running:
                try:
                    heap_used = await language_tool_manager.get_jvm_heap_usage()
                    if heap_used is not None:
                        heap_used_mb = heap_used
                except Exception:
                    # Fallback to 0 if unable to get heap usage
                    pass

        # Calculate service uptime (TASK-052G requirement)
        uptime_seconds = 0.0
        try:
            import time

            from quart import current_app

            start_time = current_app.extensions.get("service_start_time")
            if start_time:
                uptime_seconds = time.time() - start_time
        except Exception:
            # Fallback to 0 if unable to calculate uptime
            pass

        # TASK-052G format: Include jvm and uptime_seconds at top level
        health_response = {
            "service": settings.SERVICE_NAME,
            "status": overall_status,
            "message": f"Language Tool Service is {overall_status}",
            "version": "1.0.0",
            "jvm": {
                "running": jvm_running,
                "heap_used_mb": heap_used_mb,
            },
            "uptime_seconds": uptime_seconds,
            "checks": checks,
            "dependencies": dependencies,
            "environment": settings.ENVIRONMENT.value,
            "correlation_id": corr.original,
        }

        status_code = 200 if overall_status == "healthy" else 503
        return jsonify(health_response), status_code

    except Exception as e:
        logger.error(f"Health check failed: {e}", correlation_id=corr.original)
        return jsonify(
            {
                "service": settings.SERVICE_NAME,
                "status": "unhealthy",
                "message": "Health check failed",
                "version": "1.0.0",
                "jvm": {
                    "running": False,
                    "heap_used_mb": 0,
                },
                "uptime_seconds": 0.0,
                "error": str(e),
                "correlation_id": corr.original,
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
