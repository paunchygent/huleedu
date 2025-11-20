"""Health and metrics routes for API Gateway Service."""

from __future__ import annotations

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest

from huleedu_service_libs.logging_utils import create_service_logger

router = APIRouter(tags=["Health"])


@router.get("/healthz")
async def health_check() -> dict[str, str | dict]:
    """Health check endpoint following Rule 072 format."""
    logger = create_service_logger("api_gateway_service.routers.health")
    try:
        logger.info("Health check requested")
        checks = {"service_responsive": True, "dependencies_available": True}
        dependencies = {
            "redis": {"status": "healthy", "note": "Rate limiting and session storage"},
            "downstream_services": {
                "status": "healthy",
                "note": "Proxied service availability checked on request",
            },
        }

        overall_status = "healthy" if checks["dependencies_available"] else "unhealthy"

        return {
            "service": "api_gateway_service",
            "status": overall_status,
            "message": f"API Gateway Service is {overall_status}",
            "version": "1.0.0",
            "checks": checks,
            "dependencies": dependencies,
            "environment": "development",
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "service": "api_gateway_service",
            "status": "unhealthy",
            "message": "Health check failed",
            "version": "1.0.0",
            "error": str(e),
        }


@router.get("/metrics", response_class=PlainTextResponse)
@inject
async def metrics(registry: FromDishka[CollectorRegistry]):
    """Prometheus metrics endpoint."""
    logger = create_service_logger("api_gateway_service.routers.health")
    try:
        metrics_data = generate_latest(registry)
        return PlainTextResponse(content=metrics_data, media_type=CONTENT_TYPE_LATEST)
    except Exception as e:
        logger.error(f"Error generating metrics: {e}", exc_info=True)
        return PlainTextResponse(content="Error generating metrics", status_code=500)
