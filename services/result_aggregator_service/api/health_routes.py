"""Health check and metrics endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dishka import FromDishka
from huleedu_service_libs.database import DatabaseHealthChecker
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol
from prometheus_client import CollectorRegistry
from quart import Blueprint, Response, current_app, jsonify
from quart_dishka import inject

from services.result_aggregator_service.config import Settings

if TYPE_CHECKING:
    from huleedu_service_libs.quart_app import HuleEduApp

logger = create_service_logger("result_aggregator.api.health")

health_bp = Blueprint("health", __name__)


@health_bp.route("/healthz")
@inject
async def health_check(
    settings: FromDishka[Settings],
    redis_client: FromDishka[RedisClientProtocol],
) -> Response | tuple[Response, int]:
    """Health check endpoint with dependency checks."""
    try:
        # Check dependencies
        dependencies = {}
        checks = {"service_responsive": True, "dependencies_available": True}

        # Database health check (engine guaranteed to exist with new contract)
        if TYPE_CHECKING:
            assert isinstance(current_app, HuleEduApp)
        engine = current_app.database_engine
        
        try:
            health_checker = DatabaseHealthChecker(engine, "result_aggregator_service")
            summary = await health_checker.get_health_summary()
            dependencies["database"] = {"status": summary.get("status", "unknown")}
            if summary.get("status") not in ["healthy", "warning"]:
                checks["dependencies_available"] = False
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            dependencies["database"] = {"status": "unhealthy", "error": str(e)}
            checks["dependencies_available"] = False

        # Redis health check
        try:
            redis_status = await _check_redis_health(redis_client)
            dependencies["redis"] = redis_status
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            dependencies["redis"] = {"status": "unhealthy", "error": str(e)}
            checks["dependencies_available"] = False

        # Kafka health check (basic check - service can start without Kafka)
        dependencies["kafka"] = {
            "status": "healthy",
            "note": "Kafka availability checked during message consumption",
        }

        overall_status = "healthy" if checks["dependencies_available"] else "unhealthy"

        health_response = {
            "service": settings.SERVICE_NAME,
            "status": overall_status,
            "message": f"Result Aggregator Service is {overall_status}",
            "version": settings.SERVICE_VERSION,
            "checks": checks,
            "dependencies": dependencies,
            "environment": "development",  # Could be made configurable
        }

        status_code = 200 if overall_status == "healthy" else 503
        return jsonify(health_response), status_code

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify(
            {
                "service": "result_aggregator_service",
                "status": "unhealthy",
                "message": "Health check failed",
                "version": "1.0.0",
                "error": str(e),
            }
        ), 503


async def _check_redis_health(redis_client: RedisClientProtocol) -> dict:
    """Check Redis connection health."""
    try:
        # Simple ping to verify Redis connectivity
        await redis_client.ping()
        return {"status": "healthy"}
    except Exception as e:
        raise Exception(f"Redis connection failed: {e}")


@health_bp.route("/metrics")
@inject
async def metrics(registry: FromDishka[CollectorRegistry]) -> Response:
    """Prometheus metrics endpoint."""
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        metrics_data = generate_latest(registry)
        return Response(metrics_data, content_type=CONTENT_TYPE_LATEST)
    except Exception as e:
        logger.error(f"Error generating metrics: {e}")
        return Response(f"Error generating metrics: {str(e)}", status=500)
