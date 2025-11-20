"""Health and metrics routes for CJ Assessment Service.

This Blueprint provides the mandatory /healthz and /metrics endpoints
for operational monitoring and observability.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from common_core.error_enums import ErrorCode
from dishka import FromDishka
from huleedu_service_libs.database import DatabaseHealthChecker
from huleedu_service_libs.error_handling.error_detail_factory import (
    create_error_detail_with_context,
)
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.quart_app import HuleEduApp
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry
from quart import Blueprint, Response, current_app, jsonify
from quart_dishka import inject

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import ErrorResponse
from services.cj_assessment_service.protocols import CJRepositoryProtocol

health_bp = Blueprint("health_routes", __name__)


def create_error_response(
    error_code: ErrorCode, message: str, status_code: int = 500
) -> tuple[Response, int]:
    """Create a standardized error response using ErrorResponse format."""
    error_detail = create_error_detail_with_context(
        error_code=error_code,
        message=message,
        service="cj_assessment_service",
        operation="health_api_error",
        correlation_id=uuid4(),
        capture_stack=False,  # Don't capture stack for API boundary errors
        details={},
    )

    error_response = ErrorResponse(error=error_detail, status_code=status_code)

    return jsonify(error_response.model_dump()), status_code


@health_bp.route("/healthz")
@inject
async def health_check(settings: FromDishka[Settings]) -> tuple[Response, int]:
    """Standardized health check endpoint for CJ Assessment Service."""
    logger = create_service_logger("cj_assessment_service.api.health")
    try:
        logger.info("Health check requested")
        # Check database connectivity
        checks = {"service_responsive": True, "dependencies_available": True}
        dependencies = {}

        # Type-safe access to guaranteed infrastructure
        if TYPE_CHECKING:
            assert isinstance(current_app, HuleEduApp)

        engine = current_app.database_engine  # Guaranteed to exist
        try:
            health_checker = DatabaseHealthChecker(engine, settings.SERVICE_NAME)
            summary = await health_checker.get_health_summary()
            dependencies["database"] = {"status": summary.get("status", "unknown")}
            if summary.get("status") not in ["healthy", "warning"]:
                checks["dependencies_available"] = False
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            dependencies["database"] = {"status": "unhealthy", "error": str(e)}
            checks["dependencies_available"] = False

        overall_status = "healthy" if checks["dependencies_available"] else "unhealthy"

        health_response = {
            "service": settings.SERVICE_NAME,
            "status": overall_status,
            "message": f"CJ Assessment Service is {overall_status}",
            "version": settings.VERSION,
            "checks": checks,
            "dependencies": dependencies,
            "environment": settings.ENVIRONMENT.value,
        }

        status_code = 200 if overall_status == "healthy" else 503
        return jsonify(health_response), status_code

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return create_error_response(
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            message=f"Health check failed: {str(e)}",
            status_code=503,
        )


@health_bp.route("/healthz/database")
@inject
async def database_health_check(settings: FromDishka[Settings]) -> Response | tuple[Response, int]:
    """Database-specific health check endpoint with detailed metrics."""
    logger = create_service_logger("cj_assessment_service.api.health")
    try:
        # Type-safe access to guaranteed infrastructure
        if TYPE_CHECKING:
            assert isinstance(current_app, HuleEduApp)

        engine = current_app.database_engine  # Guaranteed to exist

        # Create health checker and perform comprehensive check
        health_checker = DatabaseHealthChecker(engine, settings.SERVICE_NAME)
        health_result = await health_checker.comprehensive_health_check()

        # Determine HTTP status code based on health status
        status_code = 200
        if health_result.get("overall_status") in ["unhealthy", "error"]:
            status_code = 503
        elif health_result.get("overall_status") == "warning":
            status_code = 200  # Warning is still considered healthy for load balancer

        return (jsonify(health_result), status_code)

    except Exception as e:
        logger.error(f"Database health check failed: {e}", exc_info=True)
        return create_error_response(
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            message=f"Database health check failed: {str(e)}",
            status_code=503,
        )


@health_bp.route("/healthz/database/summary")
@inject
async def database_health_summary(
    settings: FromDishka[Settings],
) -> Response | tuple[Response, int]:
    """Lightweight database health summary for frequent polling."""
    logger = create_service_logger("cj_assessment_service.api.health")
    try:
        # Type-safe access to guaranteed infrastructure
        if TYPE_CHECKING:
            assert isinstance(current_app, HuleEduApp)

        engine = current_app.database_engine  # Guaranteed to exist

        # Create health checker and get summary
        health_checker = DatabaseHealthChecker(engine, settings.SERVICE_NAME)
        summary = await health_checker.get_health_summary()

        # Determine HTTP status code
        status_code = 200 if summary.get("status") in ["healthy", "warning"] else 503

        return (jsonify(summary), status_code)

    except Exception as e:
        logger.error(f"Database health summary failed: {e}", exc_info=True)
        return create_error_response(
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            message=f"Database health summary failed: {str(e)}",
            status_code=503,
        )


@health_bp.route("/metrics")
@inject
async def metrics(registry: FromDishka[CollectorRegistry]) -> Response:
    """Prometheus metrics endpoint.

    Serves metrics in OpenMetrics format for Prometheus scraping.

    Returns:
        Prometheus-formatted metrics data
    """
    logger = create_service_logger("cj_assessment_service.api.health")
    try:
        from prometheus_client import generate_latest

        metrics_data = generate_latest(registry)
        return Response(metrics_data, content_type=CONTENT_TYPE_LATEST)
    except Exception as e:
        logger.error(f"Error generating metrics: {e}", exc_info=True)
        response, status_code = create_error_response(
            error_code=ErrorCode.PROCESSING_ERROR,
            message=f"Error generating metrics: {str(e)}",
            status_code=500,
        )
        return response


@health_bp.route("/healthz/live")
@inject
async def liveness_probe(settings: FromDishka[Settings]) -> tuple[Response, int]:
    """Kubernetes liveness probe endpoint.

    Simple check to verify the service is running.
    Returns 200 if the service is alive, 503 otherwise.

    This endpoint is intentionally lightweight and only checks
    basic service responsiveness, not dependencies.
    """
    logger = create_service_logger("cj_assessment_service.api.health")
    try:
        # Basic check - if we can handle requests, we're alive
        response = {
            "status": "alive",
            "service": settings.SERVICE_NAME,
            "message": "Service is responding",
        }
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Liveness probe failed: {e}")
        return jsonify({"status": "dead", "error": str(e)}), 503


@health_bp.route("/healthz/ready")
@inject
async def readiness_probe(
    repository: FromDishka[CJRepositoryProtocol],
    settings: FromDishka[Settings],
) -> tuple[Response, int]:
    """Kubernetes readiness probe endpoint.

    Checks if the service is ready to accept traffic.
    Returns 200 if ready, 503 if not ready.

    Checks:
    - Database connectivity
    - Active batch monitoring
    - Critical dependencies
    """
    logger = create_service_logger("cj_assessment_service.api.health")
    try:
        checks = {
            "database": False,
            "kafka": True,  # Assumed healthy if we got this far
            "batch_monitoring": True,
        }

        # Check database readiness
        try:
            async with repository.session() as session:
                # Simple query to verify DB connectivity
                from sqlalchemy import text

                result = await session.execute(text("SELECT 1"))
                _ = result.scalar()
                checks["database"] = True
        except Exception as e:
            logger.warning(f"Database readiness check failed: {e}")
            checks["database"] = False

        # Check for stuck batches (indicates monitoring is working)
        try:
            async with repository.session() as session:
                from datetime import UTC, datetime, timedelta

                from common_core.status_enums import CJBatchStateEnum
                from sqlalchemy import select

                from services.cj_assessment_service.models_db import CJBatchState

                # Count active batches
                active_states = [
                    CJBatchStateEnum.INITIALIZING,
                    CJBatchStateEnum.GENERATING_PAIRS,
                    CJBatchStateEnum.WAITING_CALLBACKS,
                    CJBatchStateEnum.SCORING,
                ]

                stmt = select(CJBatchState).where(CJBatchState.state.in_(active_states))
                result = await session.execute(stmt)
                active_batches = result.scalars().all()

                # Check for stuck batches (no activity for > 2 hours)
                stuck_threshold = datetime.now(UTC) - timedelta(hours=2)
                stuck_count = sum(
                    1 for batch in active_batches if batch.last_activity_at < stuck_threshold
                )

                # Warn if too many stuck batches
                if stuck_count > 5:
                    checks["batch_monitoring"] = False
                    logger.warning(f"Too many stuck batches: {stuck_count}")

        except Exception as e:
            logger.warning(f"Batch monitoring check failed: {e}")
            # Don't fail readiness for monitoring issues

        # Overall readiness
        is_ready = all(checks.values())

        response = {
            "status": "ready" if is_ready else "not_ready",
            "service": settings.SERVICE_NAME,
            "checks": checks,
            "message": "Service is ready to accept traffic" if is_ready else "Service is not ready",
        }

        return jsonify(response), 200 if is_ready else 503

    except Exception as e:
        logger.error(f"Readiness probe failed: {e}", exc_info=True)
        return jsonify(
            {
                "status": "not_ready",
                "error": str(e),
                "message": "Readiness probe error",
            }
        ), 503
