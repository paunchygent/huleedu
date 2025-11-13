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
    raise_authentication_error,
    raise_configuration_error,
    raise_external_service_error,
    raise_parsing_error,
    raise_rate_limit_error,
)
from services.llm_provider_service.internal_models import LLMProviderResponse
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
        system_prompt = (
            system_prompt_override
            or "You are an LLM comparison engine. Follow the caller-supplied instructions and ensure your output satisfies the required tool schema."
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
        except Exception as e:
            raise_external_service_error(
                service="llm_provider_service",
                operation="anthropic_api_request",
                external_service="anthropic_api",
                message=f"Anthropic API call failed: {str(e)}",
                correlation_id=correlation_id,
                details={"provider": "anthropic"},
            )

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

        try:
            async with self.session.post(
                endpoint,
                headers=headers,
                json=payload,
            ) as response:
                if response.status == 200:
                    response_text = await response.text()
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
                            if (
                                block.get("type") == "tool_use"
                                and block.get("name") == "comparison_result"
                            ):
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
                        raise_external_service_error(
                            service="llm_provider_service",
                            operation="anthropic_api_request",
                            external_service="anthropic_api",
                            message="No tool use found in Anthropic response",
                            correlation_id=correlation_id,
                            details={"provider": "anthropic"},
                        )

                else:
                    error_text = await response.text()
                    error_msg = f"Anthropic API error: {response.status} - {error_text}"

                    # Raise for retryable status codes to trigger retry
                    if response.status in {429, 500, 502, 503, 504}:
                        response.raise_for_status()

                    # Handle specific HTTP errors with appropriate exceptions
                    if response.status == 429:
                        raise_rate_limit_error(
                            service="llm_provider_service",
                            operation="anthropic_api_request",
                            limit=0,  # Unknown limit from API
                            window_seconds=60,
                            message=f"Rate limit exceeded: {error_text}",
                            correlation_id=correlation_id,
                            details={"provider": "anthropic", "retry_after": 60},
                        )
                    elif response.status == 401:
                        raise_authentication_error(
                            service="llm_provider_service",
                            operation="anthropic_api_request",
                            message=f"Authentication failed: {error_text}",
                            correlation_id=correlation_id,
                            details={"provider": "anthropic"},
                        )
                    else:
                        raise_external_service_error(
                            service="llm_provider_service",
                            operation="anthropic_api_request",
                            external_service="anthropic_api",
                            message=error_msg,
                            correlation_id=correlation_id,
                            details={"provider": "anthropic", "status_code": response.status},
                        )

        except aiohttp.ClientResponseError:
            # Will be retried by retry manager
            raise
        except aiohttp.ClientError:
            # Connection errors, timeouts, etc.
            raise
        except Exception as e:
            # Unexpected errors
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
