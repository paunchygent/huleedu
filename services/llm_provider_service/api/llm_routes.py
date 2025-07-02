"""LLM provider API routes."""

import time
from uuid import uuid4

from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.resilience import CircuitBreakerError, CircuitBreakerRegistry
from quart import Blueprint, Response, jsonify, request
from quart_dishka import inject

from common_core import LLMProviderType
from services.llm_provider_service.api_models import (
    LLMComparisonRequest,
    LLMComparisonResponse,
    LLMProviderListResponse,
    LLMProviderStatus,
)
from services.llm_provider_service.config import Settings
from services.llm_provider_service.metrics import get_llm_metrics
from services.llm_provider_service.protocols import LLMOrchestratorProtocol

logger = create_service_logger("llm_provider_service.api")

llm_bp = Blueprint("llm", __name__)


@llm_bp.route("/comparison", methods=["POST"])
@inject
async def generate_comparison(
    orchestrator: FromDishka[LLMOrchestratorProtocol],
    settings: FromDishka[Settings],
) -> Response | tuple[Response, int]:
    """Generate essay comparison using configured LLM provider."""
    metrics = get_llm_metrics()
    start_time = time.time()

    try:
        # Parse request
        data = await request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        try:
            comparison_request = LLMComparisonRequest(**data)
        except Exception as e:
            return jsonify({"error": f"Invalid request format: {str(e)}"}), 400

        # Generate correlation ID if not provided
        correlation_id = uuid4()
        logger.info(f"Processing comparison request with correlation_id: {correlation_id}")

        # Extract configuration overrides
        provider_override = None
        model_override = None
        temperature_override = None
        system_prompt_override = None

        if comparison_request.llm_config_overrides:
            provider_override = comparison_request.llm_config_overrides.provider_override
            model_override = comparison_request.llm_config_overrides.model_override
            temperature_override = comparison_request.llm_config_overrides.temperature_override
            system_prompt_override = comparison_request.llm_config_overrides.system_prompt_override

        # Call orchestrator
        result, error = await orchestrator.perform_comparison(
            provider=provider_override or settings.DEFAULT_LLM_PROVIDER,
            user_prompt=comparison_request.user_prompt,
            essay_a=comparison_request.essay_a,
            essay_b=comparison_request.essay_b,
            correlation_id=correlation_id,
            model_override=model_override,
            temperature_override=temperature_override,
            system_prompt_override=system_prompt_override,
        )

        # Track metrics
        _duration_ms = int((time.time() - start_time) * 1000)

        if error:
            metrics["llm_requests_total"].labels(
                provider=error.provider,
                model=model_override or "default",
                request_type="comparison",
                status="failed",
            ).inc()
            logger.error(f"Comparison request failed: {error.error_message}")
            return jsonify(
                {
                    "error": error.error_message,
                    "error_type": error.error_type.value,
                    "correlation_id": str(error.correlation_id),
                    "retry_after": error.retry_after,
                }
            ), 503 if error.is_retryable else 400

        # Success - result should not be None if no error
        if not result:
            logger.error("Orchestrator returned no result and no error")
            return jsonify(
                {
                    "error": "Internal error: No result from orchestrator",
                    "correlation_id": str(correlation_id),
                }
            ), 500

        metrics["llm_requests_total"].labels(
            provider=result.provider,
            model=result.model,
            request_type="comparison",
            status="success",
        ).inc()

        # Build response - map internal model to API response model
        response = LLMComparisonResponse(
            choice=result.choice,
            reasoning=result.reasoning,
            confidence=result.confidence,
            provider=result.provider,
            model=result.model,
            cached=result.cached,
            response_time_ms=result.response_time_ms,
            correlation_id=result.correlation_id,
            token_usage=result.token_usage,
            cost_estimate=result.cost_estimate,
            trace_id=result.trace_id,
        )

        return jsonify(response.model_dump()), 200

    except CircuitBreakerError as e:
        logger.error(f"Circuit breaker open: {e}")
        return jsonify(
            {
                "error": "Service temporarily unavailable due to provider issues",
                "details": str(e),
            }
        ), 503

    except Exception as e:
        logger.exception("Unexpected error in comparison endpoint")
        return jsonify(
            {
                "error": "Internal server error",
                "details": str(e),
            }
        ), 500


@llm_bp.route("/providers", methods=["GET"])
@inject
async def list_providers(
    settings: FromDishka[Settings],
    circuit_breaker_registry: FromDishka[CircuitBreakerRegistry],
) -> Response | tuple[Response, int]:
    """List all configured LLM providers and their status."""
    try:
        providers = []

        # Check each provider
        for provider_name in ["anthropic", "openai", "google", "openrouter"]:
            # Check if enabled
            enabled = getattr(settings, f"{provider_name.upper()}_ENABLED", False)

            # Check circuit breaker status
            circuit_breaker = circuit_breaker_registry.get(f"llm_{provider_name}")
            circuit_breaker_state = "closed"
            if circuit_breaker:
                state_info = circuit_breaker.get_state()
                circuit_breaker_state = state_info.get("state", "closed")

            # Check if API key is configured
            api_key = getattr(settings, f"{provider_name.upper()}_API_KEY", "")
            configured = bool(api_key)

            providers.append(
                LLMProviderStatus(
                    name=provider_name,
                    enabled=enabled,
                    available=enabled and configured and circuit_breaker_state == "closed",
                    circuit_breaker_state=circuit_breaker_state,
                    default_model=getattr(settings, f"{provider_name.upper()}_DEFAULT_MODEL", None),
                )
            )

        response = LLMProviderListResponse(
            providers=providers,
            default_provider=settings.DEFAULT_LLM_PROVIDER,
            selection_strategy=settings.PROVIDER_SELECTION_STRATEGY,
        )

        return jsonify(response.model_dump()), 200

    except Exception as e:
        logger.exception("Error listing providers")
        return jsonify(
            {
                "error": "Failed to list providers",
                "details": str(e),
            }
        ), 500


@llm_bp.route("/providers/<string:provider>/test", methods=["POST"])
@inject
async def test_provider(
    provider: str,
    orchestrator: FromDishka[LLMOrchestratorProtocol],
) -> Response | tuple[Response, int]:
    """Test a specific LLM provider."""
    try:
        # Convert string to enum
        try:
            provider_enum = LLMProviderType(provider)
        except ValueError:
            return jsonify({"error": f"Invalid provider: {provider}"}), 400

        success, message = await orchestrator.test_provider(provider=provider_enum)

        return jsonify(
            {
                "success": success,
                "provider": provider,
                "message": message,
            }
        ), 200

    except Exception as e:
        logger.exception(f"Error testing provider {provider}")
        return jsonify(
            {
                "error": f"Failed to test provider {provider}",
                "details": str(e),
            }
        ), 500
