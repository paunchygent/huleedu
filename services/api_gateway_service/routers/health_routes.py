"""Health and metrics routes for API Gateway Service."""

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest

logger = create_service_logger("api_gateway_service.routers.health")
router = APIRouter(tags=["Health"])


@router.get("/healthz")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "message": "API Gateway Service is healthy",
    }


@router.get("/metrics")
@inject
async def metrics(registry: FromDishka[CollectorRegistry]) -> PlainTextResponse:
    """Prometheus metrics endpoint."""
    try:
        metrics_data = generate_latest(registry)
        return PlainTextResponse(content=metrics_data, media_type=CONTENT_TYPE_LATEST)
    except Exception as e:
        logger.error(f"Error generating metrics: {e}", exc_info=True)
        return PlainTextResponse(content="Error generating metrics", status_code=500)
