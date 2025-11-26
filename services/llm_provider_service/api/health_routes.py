"""Health check routes for LLM Provider Service."""

from typing import Any, Dict

from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from quart import Blueprint, Response, jsonify
from quart_dishka import inject

from services.llm_provider_service.config import Settings

health_bp = Blueprint("health", __name__)


@health_bp.route("/healthz", methods=["GET"])
@inject
async def health_check(
    settings: FromDishka[Settings],
    redis_client: FromDishka[RedisClientProtocol],
) -> Response | tuple[Response, int]:
    """Health check endpoint."""
    logger = create_service_logger("llm_provider_service.api.health")
    logger.info("Health check requested")
    health_status: Dict[str, Any] = {
        "service": settings.SERVICE_NAME,
        "status": "healthy",
        "message": "LLM Provider Service is healthy",
        "version": "1.0.0",
        "checks": {"service_responsive": True, "dependencies_available": True},
        "dependencies": {},
        "environment": settings.ENVIRONMENT.value,
    }
    dependencies: Dict[str, Any] = {}

    # Check Redis
    try:
        await redis_client.ping()
        dependencies["redis"] = {"status": "healthy"}
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        dependencies["redis"] = {"status": "unhealthy", "error": str(e)}
        health_status["status"] = "unhealthy"
        health_status["message"] = "LLM Provider Service is unhealthy"
        health_status["checks"]["dependencies_available"] = False

    health_status["dependencies"] = dependencies

    # Add provider status
    providers = {
        "anthropic": {
            "enabled": settings.ANTHROPIC_ENABLED,
            "configured": bool(settings.ANTHROPIC_API_KEY.get_secret_value()),
        },
        "openai": {
            "enabled": settings.OPENAI_ENABLED,
            "configured": bool(settings.OPENAI_API_KEY.get_secret_value()),
        },
        "google": {
            "enabled": settings.GOOGLE_ENABLED,
            "configured": bool(settings.GOOGLE_API_KEY.get_secret_value()),
        },
        "openrouter": {
            "enabled": settings.OPENROUTER_ENABLED,
            "configured": bool(settings.OPENROUTER_API_KEY.get_secret_value()),
        },
    }
    health_status["providers"] = providers
    health_status["mock_mode"] = settings.USE_MOCK_LLM
    health_status["mock_provider"] = {
        "allowed": settings.ALLOW_MOCK_PROVIDER,
        "registered": settings.ALLOW_MOCK_PROVIDER or settings.USE_MOCK_LLM,
        "seed": settings.MOCK_PROVIDER_SEED if settings.ALLOW_MOCK_PROVIDER else None,
    }

    # Check if at least one provider is configured
    any_provider_configured = any(p["enabled"] and p["configured"] for p in providers.values())

    if not any_provider_configured:
        health_status["status"] = "unhealthy"
        health_status["message"] = "LLM Provider Service is unhealthy"
        health_status["checks"]["dependencies_available"] = False
        health_status["warnings"] = ["No LLM providers configured"]

    status_code = 200 if health_status["status"] == "healthy" else 503
    return jsonify(health_status), status_code


@health_bp.route("/metrics", methods=["GET"])
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    logger = create_service_logger("llm_provider_service.api.health")
    try:
        # Generate metrics from the default registry
        metrics_output = generate_latest()
        return Response(metrics_output, content_type=CONTENT_TYPE_LATEST)
    except Exception as e:
        logger.exception("Error generating metrics")
        return Response(f"Error generating metrics: {str(e)}", status=500)
