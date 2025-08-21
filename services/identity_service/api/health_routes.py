"""
Health check endpoint for Identity Service.

Implements standardized health checking per Rule 041.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, current_app, jsonify
from quart_dishka import inject

from services.identity_service.config import Settings

if TYPE_CHECKING:
    from huleedu_service_libs import HuleEduApp

bp = Blueprint("health", __name__)
logger = create_service_logger("identity_service.health_routes")


@bp.route("/healthz")
@inject
async def health_check(settings: FromDishka[Settings]) -> Response | tuple[Response, int]:
    """Standardized health check endpoint."""
    try:
        # Check database connectivity
        checks = {"service_responsive": True, "dependencies_available": True}
        dependencies = {}

        # Get database engine from HuleEduApp
        if TYPE_CHECKING:
            assert isinstance(current_app, HuleEduApp)
        engine = current_app.database_engine  # Guaranteed to exist with HuleEduApp

        try:
            # Simple database check
            from sqlalchemy import text

            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            dependencies["database"] = {"status": "healthy"}
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            dependencies["database"] = {"status": "unhealthy", "error": str(e)}
            checks["dependencies_available"] = False

        # Build response
        status = "healthy" if all(checks.values()) else "unhealthy"
        response_data = {
            "service": "identity_service",
            "status": status,
            "environment": settings.ENVIRONMENT,
            "checks": checks,
            "dependencies": dependencies,
        }

        status_code = 200 if status == "healthy" else 503
        return jsonify(response_data), status_code

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"service": "identity_service", "status": "unhealthy", "error": str(e)}), 503
