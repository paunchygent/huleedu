from __future__ import annotations

import time
from datetime import UTC, datetime

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Response
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from prometheus_client import REGISTRY, generate_latest

from services.websocket_service.config import settings
from services.websocket_service.protocols import WebSocketManagerProtocol

router = APIRouter()

# Track service start time
SERVICE_START_TIME = time.time()


@router.get("/healthz")
async def health_check():
    """Basic health check endpoint."""
    return {
        "service": settings.SERVICE_NAME,
        "status": "healthy",
        "environment": settings.ENVIRONMENT.value,
        "timestamp": datetime.now(UTC).isoformat(),
        "uptime_seconds": int(time.time() - SERVICE_START_TIME),
    }


@router.get("/healthz/redis")
@inject
async def redis_health(
    redis_client: FromDishka[AtomicRedisClientProtocol],
):
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
        return Response(
            content={
                "service": "redis",
                "status": "unhealthy",
                "error": str(e),
            },
            status_code=503,
        )


@router.get("/healthz/websocket")
@inject
async def websocket_health(
    websocket_manager: FromDishka[WebSocketManagerProtocol],
):
    """Check WebSocket manager health."""
    total_connections = websocket_manager.get_total_connections()

    return {
        "service": "websocket_manager",
        "status": "healthy",
        "total_connections": total_connections,
        "max_connections_per_user": settings.WEBSOCKET_MAX_CONNECTIONS_PER_USER,
    }


@router.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint."""
    return Response(
        generate_latest(REGISTRY),
        media_type="text/plain",
    )
