"""Health and metrics routes for Class Management Service."""

from __future__ import annotations

from dishka import FromDishka
from huleedu_service_libs.database import DatabaseMetrics
from huleedu_service_libs.database.health_checks import get_pool_status_safe
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from quart import Blueprint, Response, jsonify
from quart_dishka import inject
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = create_service_logger("class_management_service.api.health")
health_bp = Blueprint("health_routes", __name__)


@health_bp.route("/healthz")
@inject
async def health_check(
    engine: FromDishka[AsyncEngine], database_metrics: FromDishka[DatabaseMetrics]
) -> Response | tuple[Response, int]:
    """Health check endpoint with database connectivity verification."""
    checks = {"service_responsive": True, "dependencies_available": True}
    dependencies = {}

    # Test database connectivity
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))

        # Get connection pool status using type-safe method
        pool_stats = get_pool_status_safe(engine.pool)
        
        if pool_stats.get("status") == "degraded":
            dependencies["database"] = {
                "status": "degraded", 
                "error": pool_stats.get("error", "Pool status unavailable"),
                "pool_type": pool_stats.get("pool_type", "unknown")
            }
        else:
            dependencies["database"] = {
                "status": "healthy",
                "pool_size": pool_stats["pool_size"],
                "active_connections": pool_stats["active_connections"],
                "idle_connections": pool_stats["idle_connections"],
                "overflow": pool_stats["overflow_connections"],
                "pool_type": pool_stats.get("pool_type", "unknown"),
            }

            # Update connection pool metrics using type-safe values
            # Only update metrics if we have valid integer values
            if (isinstance(pool_stats["active_connections"], int) and 
                isinstance(pool_stats["idle_connections"], int) and
                isinstance(pool_stats["pool_size"], int) and
                isinstance(pool_stats["overflow_connections"], int)):
                database_metrics.set_connection_pool_status(
                    active=pool_stats["active_connections"],
                    idle=pool_stats["idle_connections"],
                    total=pool_stats["pool_size"] + pool_stats["active_connections"],
                    overflow=pool_stats["overflow_connections"],
                )

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        dependencies["database"] = {"status": "unhealthy", "error": str(e)}
        checks["dependencies_available"] = False

    overall_status = "healthy" if checks["dependencies_available"] else "unhealthy"

    health_status = {
        "service": "class_management_service",
        "status": overall_status,
        "message": f"Class Management Service is {overall_status}",
        "version": "1.0.0",
        "checks": checks,
        "dependencies": dependencies,
        "environment": "development",
    }

    status_code = 200 if overall_status == "healthy" else 503
    return jsonify(health_status), status_code


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
