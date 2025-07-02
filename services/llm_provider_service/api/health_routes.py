"""Health check routes for LLM Provider Service."""

from typing import Any, Dict

from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol
from prometheus_client import generate_latest
from quart import Blueprint, Response, jsonify
from quart_dishka import inject

from services.llm_provider_service.config import Settings
from services.llm_provider_service.protocols import LLMCacheManagerProtocol

logger = create_service_logger("llm_provider_service.health")

health_bp = Blueprint("health", __name__)


@health_bp.route("/healthz", methods=["GET"])
@inject
async def health_check(
    settings: FromDishka[Settings],
    redis_client: FromDishka[RedisClientProtocol],
    cache_manager: FromDishka[LLMCacheManagerProtocol],
) -> Response | tuple[Response, int]:
    """Health check endpoint."""
    health_status = {
        "service": settings.SERVICE_NAME,
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "dependencies": {},
    }
    dependencies: Dict[str, Any] = {}

    # Check Redis
    try:
        await redis_client.ping()
        dependencies["redis"] = "healthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        dependencies["redis"] = "unhealthy"
        health_status["status"] = "degraded"

    # Check Cache System (including graceful degradation status)
    try:
        cache_health = await cache_manager.is_cache_healthy()
        dependencies["cache"] = cache_health

        # If cache is degraded, mark overall status as degraded but still functional
        if cache_health.get("cache_mode") == "degraded":
            health_status["status"] = "degraded"
            warnings = health_status.get("warnings", [])
            if not isinstance(warnings, list):
                warnings = []
            warnings.append("Cache operating in degraded mode - Redis unavailable")
            health_status["warnings"] = warnings
    except Exception as e:
        logger.error(f"Cache health check failed: {e}")
        dependencies["cache"] = {"error": str(e), "cache_mode": "unhealthy"}
        health_status["status"] = "degraded"

    health_status["dependencies"] = dependencies

    # Add provider status
    providers = {
        "anthropic": {
            "enabled": settings.ANTHROPIC_ENABLED,
            "configured": bool(settings.ANTHROPIC_API_KEY),
        },
        "openai": {
            "enabled": settings.OPENAI_ENABLED,
            "configured": bool(settings.OPENAI_API_KEY),
        },
        "google": {
            "enabled": settings.GOOGLE_ENABLED,
            "configured": bool(settings.GOOGLE_API_KEY),
        },
        "openrouter": {
            "enabled": settings.OPENROUTER_ENABLED,
            "configured": bool(settings.OPENROUTER_API_KEY),
        },
    }
    health_status["providers"] = providers

    # Check if at least one provider is configured
    any_provider_configured = any(p["enabled"] and p["configured"] for p in providers.values())

    if not any_provider_configured:
        health_status["status"] = "degraded"
        health_status["warnings"] = ["No LLM providers configured"]

    status_code = 200 if health_status["status"] == "healthy" else 503
    return jsonify(health_status), status_code


@health_bp.route("/metrics", methods=["GET"])
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    try:
        # Generate metrics from the default registry
        metrics_output = generate_latest()
        return Response(metrics_output, mimetype="text/plain; version=0.0.4")
    except Exception as e:
        logger.exception("Error generating metrics")
        return Response(f"Error generating metrics: {str(e)}", status=500)
