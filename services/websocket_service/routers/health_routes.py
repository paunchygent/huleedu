from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Response
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from prometheus_client import CollectorRegistry, generate_latest

from services.websocket_service.config import Settings
from services.websocket_service.protocols import WebSocketManagerProtocol

router = APIRouter()

# Track service start time
SERVICE_START_TIME = time.time()


@router.get("/healthz")
@inject
async def health_check(
    settings: FromDishka[Settings],
) -> dict[str, Any]:
    """Basic health check endpoint."""
    logger = create_service_logger("websocket_service.routers.health")
    logger.info("Health check requested")
    return {
        "service": settings.SERVICE_NAME,
        "status": "healthy",
        "message": "WebSocket Service is healthy",
        "environment": settings.ENVIRONMENT.value,
        "timestamp": datetime.now(UTC).isoformat(),
        "uptime_seconds": int(time.time() - SERVICE_START_TIME),
    }


@router.get("/healthz/redis")
@inject
async def redis_health(
    redis_client: FromDishka[AtomicRedisClientProtocol],
    settings: FromDishka[Settings],
) -> dict[str, Any]:
    """Check Redis connectivity health."""
    try:
        # Test Redis connectivity
        await redis_client.ping()

        return {
            "service": "redis",
            "status": "healthy",
            "url": settings.REDIS_URL.replace(
                settings.REDIS_URL.split("@")[0].split("//")[1], "***:***"
            ),  # Mask credentials
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={
                "service": "redis",
                "status": "unhealthy",
                "error": str(e),
            },
        )


@router.get("/healthz/websocket")
@inject
async def websocket_health(
    websocket_manager: FromDishka[WebSocketManagerProtocol],
    settings: FromDishka[Settings],
) -> dict[str, Any]:
    """Check WebSocket manager health."""
    total_connections = websocket_manager.get_total_connections()

    return {
        "service": "websocket_manager",
        "status": "healthy",
        "total_connections": total_connections,
        "max_connections_per_user": settings.WEBSOCKET_MAX_CONNECTIONS_PER_USER,
    }


@router.get("/metrics")
@inject
async def get_metrics(
    registry: FromDishka[CollectorRegistry],
) -> Response:
    """Prometheus metrics endpoint."""
    return Response(
        generate_latest(registry),
        media_type="text/plain",
    )
