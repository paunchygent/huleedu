"""Google Gemini LLM provider implementation."""

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
from services.llm_provider_service.protocols import LLMProviderProtocol, LLMRetryManagerProtocol
from services.llm_provider_service.response_validator import validate_and_normalize_response

logger = create_service_logger("llm_provider_service.google_provider")


class GoogleProviderImpl(LLMProviderProtocol):
    """Google Gemini LLM provider implementation."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        settings: Settings,
        retry_manager: LLMRetryManagerProtocol,
    ):
        """Initialize Google provider.

        Args:
            session: HTTP client session
            settings: Service settings
            retry_manager: Retry manager for resilient requests
        """
        self.session = session
        self.settings = settings
        self.retry_manager = retry_manager
        self.api_key = settings.GOOGLE_API_KEY.get_secret_value()
        self.project_id = settings.GOOGLE_PROJECT_ID
        self.api_base = "https://generativelanguage.googleapis.com/v1beta"

    async def generate_comparison(
        self,
        user_prompt: str,
        correlation_id: UUID,
        prompt_blocks: list[dict[str, Any]] | None = None,
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
                config_key="GOOGLE_API_KEY",
                message="Google API key not configured",
                correlation_id=correlation_id,
                details={"provider": "google"},
            )

        if not self.project_id:
            raise_configuration_error(
                service="llm_provider_service",
                operation="generate_comparison",
                config_key="GOOGLE_PROJECT_ID",
                message="Google project ID not configured",
                correlation_id=correlation_id,
                details={"provider": "google"},
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
                operation_name="google_api_request",
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
                operation="google_api_request",
                external_service="google_api",
                message=f"Google API call failed: {str(e)}",
                correlation_id=correlation_id,
                details={"provider": "google"},
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
        """Make API request to Google Gemini.

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
        # Determine model and parameters
        model = model_override or self.settings.GOOGLE_DEFAULT_MODEL
        temperature = (
            temperature_override
            if temperature_override is not None
            else self.settings.LLM_DEFAULT_TEMPERATURE
        )
        max_tokens = max_tokens_override or self.settings.LLM_DEFAULT_MAX_TOKENS

        # Construct endpoint URL
        endpoint = f"{self.api_base}/models/{model}:generateContent"

        headers = {
            "Content-Type": "application/json",
        }

        # Configure structured output with JSON schema
        payload = {
            "contents": [{"parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "candidateCount": 1,
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "object",
                    "properties": {
                        "winner": {"type": "string", "enum": ["Essay A", "Essay B"]},
                        "justification": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 1, "maximum": 5},
                    },
                    "required": ["winner", "justification", "confidence"],
                },
            },
        }

        # Add API key as query parameter (Google's preferred method)
        params = {"key": self.api_key}

        try:
            async with self.session.post(
                endpoint,
                headers=headers,
                json=payload,
                params=params,
            ) as response:
                if response.status == 200:
                    response_data = await response.json()

                    # Extract content from Google response
                    if (
                        response_data.get("candidates")
                        and len(response_data["candidates"]) > 0
                        and response_data["candidates"][0].get("content")
                    ):
                        content = response_data["candidates"][0]["content"]
                        if content.get("parts") and len(content["parts"]) > 0:
                            text_content = content["parts"][0].get("text", "")

                            try:
                                # Validate and normalize response using centralized validator
                                validated_response = validate_and_normalize_response(
                                    text_content, provider="google", correlation_id=correlation_id
                                )

                                # Use validated response directly
                                # (already in assessment domain language)

                                # Convert winner string to enum value
                                if validated_response.winner == "Essay A":
                                    winner = EssayComparisonWinner.ESSAY_A
                                elif validated_response.winner == "Essay B":
                                    winner = EssayComparisonWinner.ESSAY_B
                                else:
                                    msg = f"Unexpected winner: {validated_response.winner}"
                                    raise ValueError(msg)

                                # Convert confidence from 1-5 scale to 0-1 scale for internal model
                                confidence_normalized = (validated_response.confidence - 1.0) / 4.0

                                # Google doesn't provide detailed token usage like others
                                # Estimate based on input/output length
                                prompt_tokens = len(f"{system_prompt} {user_prompt}".split())
                                completion_tokens = len(text_content.split())
                                total_tokens = prompt_tokens + completion_tokens

                                # Create response model
                                metadata: dict[str, Any] = {}
                                if prompt_sha256:
                                    metadata["prompt_sha256"] = prompt_sha256

                                response_model = LLMProviderResponse(
                                    winner=winner,
                                    justification=validated_response.justification,
                                    confidence=confidence_normalized,
                                    provider=LLMProviderType.GOOGLE,
                                    model=model,
                                    prompt_tokens=prompt_tokens,
                                    completion_tokens=completion_tokens,
                                    total_tokens=total_tokens,
                                    raw_response=response_data,
                                    metadata=metadata,
                                )

                                return response_model

                            except (json.JSONDecodeError, ValueError, KeyError) as e:
                                error_msg = f"Failed to parse Google response: {str(e)}"
                                logger.error(error_msg, extra={"response_text": text_content[:500]})
                                raise_parsing_error(
                                    service="llm_provider_service",
                                    operation="google_api_request",
                                    parse_target="json_response",
                                    message=error_msg,
                                    correlation_id=correlation_id,
                                    details={"provider": "google"},
                                )

                    raise_external_service_error(
                        service="llm_provider_service",
                        operation="google_api_request",
                        external_service="google_api",
                        message="No content in Google response",
                        correlation_id=correlation_id,
                        details={"provider": "google"},
                    )

                else:
                    error_text = await response.text()
                    error_msg = f"Google API error: {response.status} - {error_text}"

                    # Raise for retryable status codes to trigger retry
                    if response.status in {429, 500, 502, 503, 504}:
                        response.raise_for_status()

                    # Handle specific HTTP errors with appropriate exceptions
                    if response.status == 429:
                        raise_rate_limit_error(
                            service="llm_provider_service",
                            operation="google_api_request",
                            limit=0,  # Unknown limit from API
                            window_seconds=60,
                            message=f"Rate limit exceeded: {error_text}",
                            correlation_id=correlation_id,
                            details={"provider": "google", "retry_after": 60},
                        )
                    elif response.status in {401, 403}:
                        raise_authentication_error(
                            service="llm_provider_service",
                            operation="google_api_request",
                            message=f"Authentication failed: {error_text}",
                            correlation_id=correlation_id,
                            details={"provider": "google"},
                        )
                    else:
                        raise_external_service_error(
                            service="llm_provider_service",
                            operation="google_api_request",
                            external_service="google_api",
                            message=error_msg,
                            correlation_id=correlation_id,
                            details={"provider": "google", "status_code": response.status},
                        )

        except aiohttp.ClientResponseError:
            # Will be retried by retry manager
            raise
        except aiohttp.ClientError:
            # Connection errors, timeouts, etc.
            raise
        except Exception as e:
            # Unexpected errors
            error_msg = f"Unexpected error calling Google API: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise_external_service_error(
                service="llm_provider_service",
                operation="google_api_request",
                external_service="google_api",
                message=error_msg,
                correlation_id=correlation_id,
                details={"provider": "google"},
            )
