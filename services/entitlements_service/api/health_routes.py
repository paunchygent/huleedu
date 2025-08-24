"""Health and metrics endpoints for Entitlements Service.

This module provides health check and Prometheus metrics endpoints
following HuleEdu monitoring standards.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from quart import Blueprint, Response, current_app

if TYPE_CHECKING:
    from huleedu_service_libs.quart_app import HuleEduApp

logger = create_service_logger("entitlements_service.health")

# Create health blueprint
health_bp = Blueprint("health", __name__)


@health_bp.route("/healthz", methods=["GET"])
async def health_check() -> tuple[dict[str, Any], int]:
    """Health check endpoint.

    Returns:
        JSON response with health status
    """
    app: HuleEduApp = current_app._get_current_object()  # type: ignore[attr-defined]

    # Check database health
    db_healthy = False
    db_message = "Unknown"

    try:
        if "health_checker" in app.extensions:
            health_checker = app.extensions["health_checker"]
            db_healthy = await health_checker.is_healthy()
            db_message = (
                "Database connection healthy" if db_healthy else "Database connection unhealthy"
            )
        else:
            db_message = "Health checker not initialized"
    except Exception as e:
        db_message = f"Health check failed: {e}"
        logger.error(db_message)

    # Overall health status
    healthy = db_healthy

    status_code = 200 if healthy else 503

    response = {
        "status": "healthy" if healthy else "unhealthy",
        "service": "entitlements_service",
        "checks": {
            "database": {
                "status": "healthy" if db_healthy else "unhealthy",
                "message": db_message,
            },
            # Redis health could be added here
        },
    }

    logger.debug(f"Health check: {response['status']}")
    return response, status_code


@health_bp.route("/metrics", methods=["GET"])
async def metrics() -> Response:
    """Prometheus metrics endpoint.

    Returns:
        Prometheus formatted metrics
    """
    try:
        # Generate metrics in Prometheus format
        metrics_data = generate_latest()

        return Response(
            metrics_data,
            mimetype=CONTENT_TYPE_LATEST,
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )
    except Exception as e:
        logger.error(f"Error generating metrics: {e}", exc_info=True)
        return Response(
            "Error generating metrics",
            status=500,
            mimetype="text/plain",
        )
