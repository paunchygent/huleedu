"""LLM provider API routes."""

import time
from uuid import uuid4

from common_core import (
    CircuitBreakerState,
    LLMComparisonRequest,
    LLMProviderType,
    LLMQueuedResponse,
)
from dishka import FromDishka
from huleedu_service_libs.error_handling.quart import create_error_response
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.resilience import CircuitBreakerError, CircuitBreakerRegistry
from quart import Blueprint, Response, jsonify, request
from quart_dishka import inject

from services.llm_provider_service.api_models import (
    LLMProviderListResponse,
    LLMProviderStatus,
    ModelInfoResponse,
    ModelManifestResponse,
)
from services.llm_provider_service.config import Settings
from services.llm_provider_service.exceptions import HuleEduError
from services.llm_provider_service.implementations.trace_context_manager_impl import (
    TraceContextManagerImpl,
)
from services.llm_provider_service.internal_models import LLMQueuedResult
from services.llm_provider_service.manifest import ProviderName, list_models
from services.llm_provider_service.metrics import get_llm_metrics
from services.llm_provider_service.protocols import LLMOrchestratorProtocol

logger = create_service_logger("llm_provider_service.api")

llm_bp = Blueprint("llm", __name__)


@llm_bp.route("/comparison", methods=["POST"])
@inject
async def generate_comparison(
    orchestrator: FromDishka[LLMOrchestratorProtocol],
    tracer: FromDishka[TraceContextManagerImpl],
) -> Response | tuple[Response, int]:
    """Generate essay comparison using configured LLM provider."""
    metrics = get_llm_metrics()
    start_time = time.time()

    try:
        # Parse request first to get correlation_id
        data = await request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        try:
            comparison_request = LLMComparisonRequest(**data)
        except Exception as e:
            return jsonify({"error": f"Invalid request format: {str(e)}"}), 400

        # Use correlation_id from request if provided, otherwise generate a new one
        correlation_id = comparison_request.correlation_id or uuid4()

        # Start tracing for the API request
        with tracer.start_api_request_span("comparison", correlation_id):
            tracer.add_span_event("request_started", {"correlation_id": str(correlation_id)})

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
                system_prompt_override = (
                    comparison_request.llm_config_overrides.system_prompt_override
                )

            # Require explicit provider configuration
            if not provider_override:
                logger.warning(
                    "Request missing required provider configuration, correlation_id: %s",
                    correlation_id,
                )
                return jsonify(
                    {
                        "error": "Provider configuration required",
                        "details": "llm_config_overrides.provider_override must be specified",
                        "correlation_id": str(correlation_id),
                    }
                ), 400

            # Add provider info to span
            tracer.set_span_attributes(
                {
                    "llm.provider": provider_override.value if provider_override else "unknown",
                    "llm.model": str(model_override) if model_override is not None else "default",
                }
            )

            # Call orchestrator
            try:
                result = await orchestrator.perform_comparison(
                    provider=provider_override,
                    user_prompt=comparison_request.user_prompt,
                    prompt_blocks=comparison_request.prompt_blocks,
                    correlation_id=correlation_id,
                    model_override=model_override,
                    temperature_override=temperature_override,
                    system_prompt_override=system_prompt_override,
                    callback_topic=comparison_request.callback_topic,
                    request_metadata=comparison_request.metadata,
                )
            except HuleEduError as error:
                # Track metrics for error
                _duration_ms = int((time.time() - start_time) * 1000)
                tracer.mark_span_error(error)

                # Extract provider info for metrics
                provider_for_metrics = provider_override or "unknown"
                metrics["llm_requests_total"].labels(
                    provider=provider_for_metrics,
                    model=model_override or "default",
                    request_type="comparison",
                    status="failed",
                ).inc()

                logger.error(f"Comparison request failed: {str(error)}")

                # Use service libraries error response factory
                error_response, status_code = create_error_response(error.error_detail)
                return jsonify(error_response), status_code

            # Success - result should not be None
            if not result:
                logger.error("Orchestrator returned no result")
                return jsonify(
                    {
                        "error": "Internal error: No result from orchestrator",
                        "correlation_id": str(correlation_id),
                    }
                ), 500

            # ARCHITECTURAL TRUTH: ALL LLM requests are queued - no immediate responses
            # Always expect LLMQueuedResult as orchestrator should never return immediate responses
            if not isinstance(result, LLMQueuedResult):
                logger.error(f"Orchestrator returned non-queued result: {type(result)}")
                return jsonify(
                    {
                        "error": "Internal error: Expected queued result",
                        "correlation_id": str(correlation_id),
                    }
                ), 500

            metrics["llm_requests_total"].labels(
                provider=result.provider,
                model=model_override or "default",
                request_type="comparison",
                status="queued",
            ).inc()

            # Build queued response - callback will be delivered to specified topic
            queued_response = LLMQueuedResponse(
                queue_id=result.queue_id,
                status=result.status,
                message=(
                    f"Request queued for processing. "
                    f"Result will be delivered via callback to topic: "
                    f"{comparison_request.callback_topic}"
                ),
                estimated_wait_minutes=result.estimated_wait_minutes,
            )

            logger.info(f"Request queued with ID: {result.queue_id}")
            tracer.add_span_event("request_completed", {"status": "queued"})
            return jsonify(queued_response.model_dump()), 202

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
            circuit_breaker_state = CircuitBreakerState.CLOSED.value
            if circuit_breaker:
                state_info = circuit_breaker.get_state()
                circuit_breaker_state = state_info.get("state", CircuitBreakerState.CLOSED.value)

            # Check if API key is configured
            api_key = getattr(settings, f"{provider_name.upper()}_API_KEY", "")
            configured = bool(api_key)

            providers.append(
                LLMProviderStatus(
                    name=provider_name,
                    enabled=enabled,
                    available=enabled
                    and configured
                    and circuit_breaker_state == CircuitBreakerState.CLOSED.value,
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

        correlation_id = uuid4()
        success = await orchestrator.test_provider(
            provider=provider_enum, correlation_id=correlation_id
        )

        return jsonify(
            {
                "success": success,
                "provider": provider,
                "message": "Provider operational" if success else "Provider unavailable",
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


@llm_bp.route("/models", methods=["GET"])
async def get_models() -> Response | tuple[Response, int]:
    """Get available LLM models grouped by provider.

    Query Parameters:
        provider (optional): Filter by specific provider (e.g., 'anthropic', 'openai')
        include_deprecated (optional): Include deprecated models (default: false)

    Returns:
        200: ModelManifestResponse with models grouped by provider
        400: Invalid provider name
        500: Internal error
    """
    try:
        # Parse query parameters
        provider_filter = request.args.get("provider")
        include_deprecated = request.args.get("include_deprecated", "false").lower() == "true"

        # Validate provider if specified
        provider_enum = None
        if provider_filter:
            try:
                provider_enum = ProviderName(provider_filter.lower())
            except ValueError:
                valid_providers = [p.value for p in ProviderName if p != ProviderName.MOCK]
                return jsonify(
                    {
                        "error": f"Invalid provider: {provider_filter}",
                        "valid_providers": valid_providers,
                    }
                ), 400

        # Get models from manifest
        models = list_models(provider_enum)

        # Filter out deprecated models unless explicitly requested
        if not include_deprecated:
            models = [m for m in models if not m.is_deprecated]

        # Filter out MOCK provider (internal testing only)
        models = [m for m in models if m.provider != ProviderName.MOCK]

        # Group models by provider
        providers_dict: dict[str, list[ModelInfoResponse]] = {}
        for model in models:
            provider_name = model.provider.value
            if provider_name not in providers_dict:
                providers_dict[provider_name] = []

            # Convert ModelConfig to ModelInfoResponse
            model_info = ModelInfoResponse(
                model_id=model.model_id,
                provider=model.provider.value,
                display_name=model.display_name,
                model_family=model.model_family,
                max_tokens=model.max_tokens,
                context_window=model.context_window,
                supports_streaming=model.supports_streaming,
                capabilities=model.capabilities,
                cost_per_1k_input_tokens=model.cost_per_1k_input_tokens,
                cost_per_1k_output_tokens=model.cost_per_1k_output_tokens,
                is_deprecated=model.is_deprecated,
                release_date=model.release_date,
                recommended_for=model.recommended_for,
            )
            providers_dict[provider_name].append(model_info)

        # Build response
        response = ModelManifestResponse(
            providers=providers_dict,
            total_models=len(models),
        )

        logger.info(
            f"Manifest query returned {len(models)} models "
            f"(provider_filter={provider_filter}, include_deprecated={include_deprecated})"
        )

        return jsonify(response.model_dump()), 200

    except Exception as e:
        logger.exception("Error retrieving model manifest")
        return jsonify(
            {
                "error": "Failed to retrieve model manifest",
                "details": str(e),
            }
        ), 500


@llm_bp.route("/status/<string:queue_id>", methods=["GET"])
@inject
async def get_queue_status(
    queue_id: str,
    tracer: FromDishka[TraceContextManagerImpl],
) -> Response | tuple[Response, int]:
    """Get status of a queued request."""
    correlation_id = uuid4()

    try:
        with tracer.start_api_request_span("get_queue_status", correlation_id):
            # For now, return 404 for all queue IDs since queue persistence isn't implemented
            return jsonify({"error": f"Queue ID {queue_id} not found"}), 404
    except Exception as e:
        logger.error(
            "Error getting queue status",
            error=str(e),
            queue_id=queue_id,
            correlation_id=str(correlation_id),
        )
        return jsonify({"error": f"Failed to get status: {e}"}), 500


@llm_bp.route("/results/<string:queue_id>", methods=["GET"])
@inject
async def get_queue_results(
    queue_id: str,
    tracer: FromDishka[TraceContextManagerImpl],
) -> Response | tuple[Response, int]:
    """Get results of a queued request."""
    correlation_id = uuid4()

    try:
        with tracer.start_api_request_span("get_queue_results", correlation_id):
            # For now, return 404 for all queue IDs since queue persistence isn't implemented
            return jsonify({"error": f"Queue ID {queue_id} not found"}), 404
    except Exception as e:
        logger.error(
            "Error getting queue results",
            error=str(e),
            queue_id=queue_id,
            correlation_id=str(correlation_id),
        )
        return jsonify({"error": f"Failed to get results: {e}"}), 500
