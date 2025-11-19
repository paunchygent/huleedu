"""Anthropic LLM provider implementation."""

import hashlib
import json
from typing import Any
from uuid import UUID

import aiohttp
from common_core import EssayComparisonWinner, LLMProviderType
from huleedu_service_libs.logging_utils import create_service_logger

from services.llm_provider_service.config import Settings
from services.llm_provider_service.exceptions import (
    HuleEduError,
    raise_configuration_error,
    raise_external_service_error,
    raise_parsing_error,
)
from services.llm_provider_service.internal_models import LLMProviderResponse
from services.llm_provider_service.metrics import get_llm_metrics
from services.llm_provider_service.model_manifest import ProviderName
from services.llm_provider_service.protocols import LLMProviderProtocol, LLMRetryManagerProtocol
from services.llm_provider_service.response_validator import validate_and_normalize_response

logger = create_service_logger("llm_provider_service.anthropic_provider")


class AnthropicProviderImpl(LLMProviderProtocol):
    """Anthropic/Claude LLM provider implementation."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        settings: Settings,
        retry_manager: LLMRetryManagerProtocol,
    ):
        """Initialize Anthropic provider.

        Args:
            session: HTTP client session
            settings: Service settings
            retry_manager: Retry manager for resilient requests
        """
        self.session = session
        self.settings = settings
        self.retry_manager = retry_manager
        self.api_key = settings.ANTHROPIC_API_KEY.get_secret_value()
        self.api_base = "https://api.anthropic.com/v1"

        # Log default model configuration from manifest
        try:
            default_config = settings.get_model_from_manifest(ProviderName.ANTHROPIC)
            logger.info(
                "Anthropic provider initialized with manifest configuration",
                extra={
                    "default_model": default_config.model_id,
                    "display_name": default_config.display_name,
                    "api_version": default_config.api_version,
                    "structured_output_method": default_config.structured_output_method.value,
                    "max_tokens": default_config.max_tokens,
                    "context_window": default_config.context_window,
                    "capabilities": default_config.capabilities,
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to load manifest configuration; using hardcoded defaults",
                extra={"error": str(e)},
            )

        self.metrics = get_llm_metrics()

    async def generate_comparison(
        self,
        user_prompt: str,
        correlation_id: UUID,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> LLMProviderResponse:
        """Generate LLM comparison response.

        Args:
            user_prompt: Complete comparison prompt with essays embedded
            correlation_id: Request correlation ID for tracing
            system_prompt_override: Optional system prompt override
            model_override: Optional model override
            temperature_override: Optional temperature override
            max_tokens_override: Optional max tokens override

        Returns:
            The LLM provider response containing comparison result

        Raises:
            HuleEduError: On any failure to generate comparison
        """
        if not self.api_key:
            raise_configuration_error(
                service="llm_provider_service",
                operation="generate_comparison",
                config_key="ANTHROPIC_API_KEY",
                message="Anthropic API key not configured",
                correlation_id=correlation_id,
                details={"provider": "anthropic"},
            )

        # Use the complete prompt with essays already embedded
        full_prompt = user_prompt
        prompt_sha256 = hashlib.sha256(full_prompt.encode("utf-8")).hexdigest()

        # Use system prompt from override or default comparison prompt
        system_prompt = system_prompt_override or (
            "You are an LLM comparison engine. Follow the caller-supplied "
            "instructions and ensure your output satisfies the required tool schema."
        )

        # Execute with retry
        try:
            result = await self.retry_manager.with_retry(
                operation=self._make_api_request,
                operation_name="anthropic_api_request",
                system_prompt=system_prompt,
                user_prompt=full_prompt,
                correlation_id=correlation_id,
                model_override=model_override,
                temperature_override=temperature_override,
                max_tokens_override=max_tokens_override,
                prompt_sha256=prompt_sha256,
            )
            # Type assert since retry manager returns Any
            return result  # type: ignore
        except HuleEduError:
            # Preserve existing structured error details from deeper layers
            raise
        except Exception as e:
            error_details = self._build_error_details_from_exception(e)
            http_status = error_details.get("http_status")
            raise_external_service_error(
                service="llm_provider_service",
                operation="anthropic_api_request",
                external_service="anthropic_api",
                message=f"Anthropic API call failed: {str(e)}",
                correlation_id=correlation_id,
                status_code=http_status
                if isinstance(http_status, int) and http_status > 0
                else None,
                **error_details,
            )

    def _build_error_details_from_exception(self, exc: Exception) -> dict[str, Any]:
        """Construct Anthropic-specific error detail context from an exception.

        This enriches ErrorDetail.details for CJ-facing diagnostics without
        changing the high-level ErrorCode semantics (EXTERNAL_SERVICE_ERROR, etc.).
        """

        details: dict[str, Any] = {"provider": "anthropic"}
        http_status: int = 0
        error_type = "unexpected"
        retryable = False
        error_text: str | None = None

        if isinstance(exc, aiohttp.ClientResponseError):
            http_status = exc.status or 0
            # When we construct ClientResponseError ourselves we set message to the raw body
            error_text = getattr(exc, "message", None)
            if http_status == 429:
                error_type = "rate_limit"
                retryable = True
            elif http_status == 401:
                error_type = "authentication"
            elif http_status >= 500:
                error_type = "server_error"
                retryable = http_status in {500, 502, 503, 504}
            elif http_status >= 400:
                error_type = "client_error"
        elif isinstance(exc, aiohttp.ClientError):
            http_status = 0
            error_type = "connection_error"
            retryable = True
            error_text = str(exc)
        else:
            http_status = 0
            error_type = "unexpected"
            retryable = False
            error_text = str(exc)

        provider_error_code = "unknown"
        provider_error_type: str | None = None
        provider_error_message: str | None = None
        if error_text:
            code, err_type, msg = self._parse_anthropic_error_json(error_text)
            if code:
                provider_error_code = code
            provider_error_type = err_type
            provider_error_message = msg

        details.update(
            {
                "http_status": http_status,
                "error_type": error_type,
                "retryable": retryable,
                "provider_error_code": provider_error_code,
            }
        )
        if provider_error_type:
            details["provider_error_type"] = provider_error_type
        if provider_error_message:
            details["provider_error_message"] = provider_error_message[:500]
        return details

    @staticmethod
    def _parse_anthropic_error_json(raw: str) -> tuple[str | None, str | None, str | None]:
        """Best-effort parsing of Anthropic JSON error payloads.

        Expected shape: {"error": {"type": "...", "code": "...", "message": "..."}}.
        Returns (code, type, message) when available, otherwise (None, None, None).
        """

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None, None, None
        if not isinstance(data, dict):
            return None, None, None
        err = data.get("error")
        if not isinstance(err, dict):
            return None, None, None

        code_val = err.get("code") or err.get("type")
        code = code_val if isinstance(code_val, str) else None
        err_type = err.get("type") if isinstance(err.get("type"), str) else None
        msg = err.get("message") if isinstance(err.get("message"), str) else None
        return code, err_type, msg

    async def _make_api_request(
        self,
        system_prompt: str,
        user_prompt: str,
        correlation_id: UUID,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
        prompt_sha256: str | None = None,
    ) -> LLMProviderResponse:
        """Make API request to Anthropic.

        Args:
            system_prompt: System prompt
            user_prompt: User prompt with essays
            correlation_id: Request correlation ID for tracing
            model_override: Optional model override
            temperature_override: Optional temperature override
            max_tokens_override: Optional max tokens override

        Returns:
            The LLM provider response

        Raises:
            HuleEduError: On any failure to make API request
        """
        endpoint = f"{self.api_base}/messages"

        # Determine model and get manifest configuration
        model = model_override or self.settings.ANTHROPIC_DEFAULT_MODEL

        # Get API version and configuration from manifest
        api_version = "2023-06-01"  # Fallback
        try:
            model_config = self.settings.get_model_from_manifest(ProviderName.ANTHROPIC, model)
            api_version = model_config.api_version

            # Log model selection
            logger.info(
                "Using Anthropic model from manifest",
                extra={
                    "model_id": model_config.model_id,
                    "display_name": model_config.display_name,
                    "api_version": api_version,
                    "using_override": model_override is not None,
                    "correlation_id": str(correlation_id),
                },
            )
        except ValueError:
            # Model not in manifest - log warning and use fallback
            logger.warning(
                "Model not found in manifest; using hardcoded API version",
                extra={
                    "model": model,
                    "fallback_api_version": api_version,
                    "correlation_id": str(correlation_id),
                },
            )

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": api_version,
            "content-type": "application/json",
        }

        temperature = (
            temperature_override
            if temperature_override is not None
            else self.settings.LLM_DEFAULT_TEMPERATURE
        )
        max_tokens = max_tokens_override or self.settings.LLM_DEFAULT_MAX_TOKENS

        # Define tool for structured comparison response
        tools = [
            {
                "name": "comparison_result",
                "description": "Essay comparison result",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "winner": {"type": "string", "enum": ["Essay A", "Essay B"]},
                        "justification": {
                            "type": "string",
                            "maxLength": 50,
                            "description": "Brief explanation (max 50 chars)",
                        },
                        "confidence": {"type": "number", "minimum": 1, "maximum": 5},
                    },
                    "required": ["winner", "justification", "confidence"],
                },
            }
        ]

        payload = {
            "model": model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "tools": tools,
            "tool_choice": {"type": "tool", "name": "comparison_result"},
        }

        response_text = await self._perform_http_request_with_metrics(
            endpoint=endpoint,
            headers=headers,
            payload=payload,
            correlation_id=correlation_id,
            model=model,
        )

        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(
                f"Failed to parse Anthropic response as JSON: {e}",
                extra={"response_text": response_text[:500]},
            )
            raise_parsing_error(
                service="llm_provider_service",
                operation="anthropic_api_request",
                parse_target="json",
                message=f"Failed to parse Anthropic response: {str(e)}",
                correlation_id=correlation_id,
                details={"provider": "anthropic"},
            )

        # Log the structure for debugging
        logger.debug(
            "Anthropic response structure",
            extra={
                "has_content": "content" in response_data,
                "content_type": type(response_data.get("content")).__name__,
                "content_length": len(response_data.get("content", []))
                if isinstance(response_data.get("content"), list)
                else 0,
            },
        )

        # Extract tool use from Anthropic response
        tool_result = None
        if isinstance(response_data.get("content"), list):
            for block in response_data["content"]:
                if block.get("type") == "tool_use" and block.get("name") == "comparison_result":
                    tool_result = block.get("input", {})
                    break

        if tool_result:
            try:
                # Validate and normalize response using centralized validator
                validated_response = validate_and_normalize_response(
                    tool_result, provider="anthropic", correlation_id=correlation_id
                )

                # Use validated response directly
                # (already in assessment domain language)

                # Convert winner string to enum value
                if validated_response.winner == "Essay A":
                    winner = EssayComparisonWinner.ESSAY_A
                elif validated_response.winner == "Essay B":
                    winner = EssayComparisonWinner.ESSAY_B
                else:
                    winner = EssayComparisonWinner.ERROR

                # Get token usage
                usage = response_data.get("usage", {})
                prompt_tokens = usage.get("input_tokens", 0)
                completion_tokens = usage.get("output_tokens", 0)
                total_tokens = prompt_tokens + completion_tokens

                # Convert confidence from 1-5 scale to 0-1 scale for internal model
                confidence_normalized = (validated_response.confidence - 1.0) / 4.0

                # Create response model
                metadata: dict[str, Any] = {}
                if prompt_sha256:
                    metadata["prompt_sha256"] = prompt_sha256

                response_model = LLMProviderResponse(
                    winner=winner,
                    justification=validated_response.justification,
                    confidence=confidence_normalized,
                    provider=LLMProviderType.ANTHROPIC,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    raw_response=response_data,
                    metadata=metadata,
                )

                return response_model

            except (ValueError, KeyError, TypeError) as e:
                error_msg = f"Failed to parse Anthropic tool response: {str(e)}"
                logger.error(error_msg, extra={"tool_result": str(tool_result)[:500]})
                raise_parsing_error(
                    service="llm_provider_service",
                    operation="anthropic_api_request",
                    parse_target="tool_response",
                    message=error_msg,
                    correlation_id=correlation_id,
                    details={"provider": "anthropic"},
                )
        else:
            # Log the full response for debugging
            logger.error(
                "No tool use found in Anthropic response",
                extra={"response_data": str(response_data)[:1000]},
            )

            if self.metrics:
                # error_type values:
                # - rate_limit, authentication, server_error, client_error
                # - connection_error, unexpected (non-HTTP failures)
                # - invalid_response (HTTP 200 with malformed or missing tool payload)
                api_errors = self.metrics.get("llm_provider_api_errors_total")
                provider_errors = self.metrics.get("llm_provider_errors_total")
                if api_errors is not None:
                    api_errors.labels(
                        provider="anthropic",
                        error_type="invalid_response",
                        http_status_code="200",
                    ).inc()
                if provider_errors is not None:
                    provider_errors.labels(
                        provider="anthropic",
                        model=model,
                        error_type="invalid_response",
                    ).inc()

            raise_external_service_error(
                service="llm_provider_service",
                operation="anthropic_api_request",
                external_service="anthropic_api",
                message="No tool use found in Anthropic response",
                correlation_id=correlation_id,
                details={
                    "provider": "anthropic",
                    "http_status": 200,
                    "error_type": "invalid_response",
                    "retryable": False,
                    "provider_error_code": "invalid_response",
                },
            )

    async def _perform_http_request_with_metrics(
        self,
        *,
        endpoint: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        correlation_id: UUID,
        model: str,
    ) -> str:
        """Make a request to the Anthropic API and record error diagnostics."""

        try:
            async with self.session.post(
                endpoint,
                headers=headers,
                json=payload,
            ) as response:
                if response.status == 200:
                    return await response.text()

                error_text = await response.text()
                error_msg = f"Anthropic API error: {response.status} - {error_text}"

                # Record API error metrics. error_type semantics:
                # - rate_limit, authentication, server_error, client_error
                # - connection_error, unexpected (non-HTTP failures)
                # - invalid_response (HTTP 200 with malformed body, recorded separately)
                error_type = "unknown"
                if response.status == 429:
                    error_type = "rate_limit"
                elif response.status == 401:
                    error_type = "authentication"
                elif response.status >= 500:
                    error_type = "server_error"
                elif response.status >= 400:
                    error_type = "client_error"

                if self.metrics:
                    api_errors = self.metrics.get("llm_provider_api_errors_total")
                    provider_errors = self.metrics.get("llm_provider_errors_total")
                    if api_errors is not None:
                        api_errors.labels(
                            provider="anthropic",
                            error_type=error_type,
                            http_status_code=str(response.status),
                        ).inc()
                    if provider_errors is not None:
                        provider_errors.labels(
                            provider="anthropic",
                            model=model,
                            error_type=error_type,
                        ).inc()

                # Log detailed error info
                log_extra = {
                    "status_code": response.status,
                    "error_text": error_text[:1000],
                    "correlation_id": str(correlation_id),
                    "provider": "anthropic",
                }

                # Capture rate limit headers if present
                for header in ["x-ratelimit-remaining", "x-ratelimit-reset", "retry-after"]:
                    if val := response.headers.get(header):
                        log_extra[header] = val

                logger.error(f"Anthropic API failure: {response.status}", extra=log_extra)

                # For HTTP error statuses, raise ClientResponseError so the retry
                # manager can apply its policies based on the status code.
                raise aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=(),
                    status=response.status,
                    message=error_text,
                    headers=response.headers,
                )

        except aiohttp.ClientResponseError:
            # Will be retried by retry manager
            raise
        except aiohttp.ClientError:
            # Connection errors, timeouts, etc.
            if self.metrics:
                api_errors = self.metrics.get("llm_provider_api_errors_total")
                provider_errors = self.metrics.get("llm_provider_errors_total")
                if api_errors is not None:
                    api_errors.labels(
                        provider="anthropic",
                        error_type="connection_error",
                        http_status_code="0",
                    ).inc()
                if provider_errors is not None:
                    provider_errors.labels(
                        provider="anthropic",
                        model=model,
                        error_type="connection_error",
                    ).inc()
            raise
        except Exception as e:
            # Unexpected errors
            if self.metrics:
                api_errors = self.metrics.get("llm_provider_api_errors_total")
                provider_errors = self.metrics.get("llm_provider_errors_total")
                if api_errors is not None:
                    api_errors.labels(
                        provider="anthropic",
                        error_type="unexpected",
                        http_status_code="0",
                    ).inc()
                if provider_errors is not None:
                    provider_errors.labels(
                        provider="anthropic",
                        model=model,
                        error_type="unexpected",
                    ).inc()

            error_msg = f"Unexpected error calling Anthropic API: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise_external_service_error(
                service="llm_provider_service",
                operation="anthropic_api_request",
                external_service="anthropic_api",
                message=error_msg,
                correlation_id=correlation_id,
                details={"provider": "anthropic"},
            )
