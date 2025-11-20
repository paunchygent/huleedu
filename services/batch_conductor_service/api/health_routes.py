"""Health and metrics routes for Batch Conductor Service."""

from __future__ import annotations

from typing import Any

from dishka import FromDishka
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from quart import Blueprint, Response, jsonify
from quart_dishka import inject

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from services.batch_conductor_service.config import Settings
from services.batch_conductor_service.protocols import BatchStateRepositoryProtocol

health_bp = Blueprint("health_routes", __name__)


@health_bp.route("/healthz")
@inject
async def health_check(
    redis_client: FromDishka[AtomicRedisClientProtocol],
    batch_state_repo: FromDishka[BatchStateRepositoryProtocol],
    settings: FromDishka[Settings],
) -> Response | tuple[Response, int]:
    """Health check endpoint compliant with Rule 072 format."""
    logger = create_service_logger("batch_conductor_service.api.health")
    logger.info("Health check requested")
    # Initialize checks and dependencies
    checks: dict[str, bool] = {
        "service_responsive": True,
        "dependencies_available": True,
    }
    dependencies: dict[str, dict[str, Any]] = {}
    overall_status = "healthy"
    message = "Batch Conductor Service is healthy"

    # Check Redis connectivity
    try:
        await redis_client.ping()
        dependencies["redis"] = {"status": "healthy", "message": "Redis connection successful"}
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        dependencies["redis"] = {
            "status": "unhealthy",
            "message": f"Redis connection failed: {str(e)}",
        }
        checks["dependencies_available"] = False
        overall_status = "degraded"
        message = "Batch Conductor Service is degraded - Redis unavailable"

    # Check PostgreSQL connectivity (if configured)
    if settings.ENABLE_POSTGRES_PERSISTENCE:
        try:
            # Attempt a simple query to check database connectivity
            test_batch_id = "health-check-test"
            await batch_state_repo.get_completed_phases(test_batch_id)
            dependencies["postgresql"] = {
                "status": "healthy",
                "message": "PostgreSQL connection successful",
            }
        except Exception as e:
            logger.error(f"PostgreSQL health check failed: {e}")
            dependencies["postgresql"] = {
                "status": "unhealthy",
                "message": f"PostgreSQL connection failed: {str(e)}",
            }
            # PostgreSQL is optional, so don't degrade overall status
            # unless it's the primary store
            if not settings.USE_REDIS_FOR_STATE:
                checks["dependencies_available"] = False
                overall_status = "degraded"
                message = "Batch Conductor Service is degraded - PostgreSQL unavailable"
    else:
        dependencies["postgresql"] = {
            "status": "not_configured",
            "message": "PostgreSQL persistence not enabled",
        }

    # Note: Essay Lifecycle Service is checked dynamically during operations
    # Not checked here to avoid cascading health check failures
    dependencies["essay_lifecycle_service"] = {
        "status": "not_checked",
        "message": "Checked dynamically during pipeline operations",
        "url": settings.ESSAY_LIFECYCLE_SERVICE_URL,
    }

    # Build Rule 072 compliant response
    health_response = {
        "service": settings.SERVICE_NAME,
        "status": overall_status,
        "message": message,
        "version": "1.0.0",  # TODO: Get from package version
        "checks": checks,
        "dependencies": dependencies,
        "environment": settings.ENVIRONMENT.value,
    }

    status_code = 200 if overall_status == "healthy" else 503
    return jsonify(health_response), status_code


@health_bp.route("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    logger = create_service_logger("batch_conductor_service.api.health")
    try:
        metrics_data = generate_latest(REGISTRY)
        response = Response(metrics_data, content_type=CONTENT_TYPE_LATEST)
        return response
    except Exception as e:
        logger.error(f"Error generating metrics: {e}", exc_info=True)
        return Response("Error generating metrics", status=500)
