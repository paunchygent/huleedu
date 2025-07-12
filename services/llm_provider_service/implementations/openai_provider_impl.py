"""OpenAI LLM provider implementation."""

import json
from uuid import UUID

import aiohttp
from huleedu_service_libs.logging_utils import create_service_logger

from common_core import EssayComparisonWinner, LLMProviderType
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

logger = create_service_logger("llm_provider_service.openai_provider")


class OpenAIProviderImpl(LLMProviderProtocol):
    """OpenAI/GPT LLM provider implementation."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        settings: Settings,
        retry_manager: LLMRetryManagerProtocol,
    ):
        """Initialize OpenAI provider.

        Args:
            session: HTTP client session
            settings: Service settings
            retry_manager: Retry manager for resilient requests
        """
        self.session = session
        self.settings = settings
        self.retry_manager = retry_manager
        self.api_key = settings.OPENAI_API_KEY
        self.api_base = "https://api.openai.com/v1"

    async def generate_comparison(
        self,
        user_prompt: str,
        essay_a: str,
        essay_b: str,
        correlation_id: UUID,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> LLMProviderResponse:
        """Generate LLM comparison response.

        Args:
            user_prompt: The comparison prompt template
            essay_a: First essay to compare
            essay_b: Second essay to compare
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
                config_key="OPENAI_API_KEY",
                message="OpenAI API key not configured",
                correlation_id=correlation_id,
                details={"provider": "openai"},
            )

        # Prepare the full prompt with essays
        full_prompt = self._format_comparison_prompt(user_prompt, essay_a, essay_b)

        # Use system prompt from override or default comparison prompt
        system_prompt = (
            system_prompt_override
            or "You are an expert essay evaluator. "
            "Compare the two essays and return your analysis as JSON. "
            "You MUST respond with a JSON object containing exactly these fields: "
            '{"winner": "Essay A" or "Essay B", "justification": "brief explanation '
            '(max 50 chars)", '
            '"confidence": 1.0-5.0}. '
            "The winner must be either 'Essay A' or 'Essay B', justification must be brief "
            "(max 50 characters), "
            "and confidence must be a float between 1.0 and 5.0."
        )

        # Execute with retry
        try:
            result = await self.retry_manager.with_retry(
                operation=self._make_api_request,
                operation_name="openai_api_request",
                system_prompt=system_prompt,
                user_prompt=full_prompt,
                correlation_id=correlation_id,
                model_override=model_override,
                temperature_override=temperature_override,
                max_tokens_override=max_tokens_override,
            )
            # Type assert since retry manager returns Any
            return result  # type: ignore
        except Exception as e:
            raise_external_service_error(
                service="llm_provider_service",
                operation="openai_api_request",
                external_service="openai_api",
                message=f"OpenAI API call failed: {str(e)}",
                correlation_id=correlation_id,
                details={"provider": "openai"},
            )

    async def _make_api_request(
        self,
        system_prompt: str,
        user_prompt: str,
        correlation_id: UUID,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> LLMProviderResponse:
        """Make API request to OpenAI.

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
        endpoint = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Determine model and parameters
        model = model_override or self.settings.OPENAI_DEFAULT_MODEL
        temperature = (
            temperature_override
            if temperature_override is not None
            else self.settings.LLM_DEFAULT_TEMPERATURE
        )
        max_tokens = max_tokens_override or self.settings.LLM_DEFAULT_MAX_TOKENS

        # Configure structured output with simplified JSON schema
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "comparison",
                    "strict": False,  # Allow flexible parsing for faster processing
                    "schema": {
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
                },
            },
        }

        try:
            async with self.session.post(
                endpoint,
                headers=headers,
                json=payload,
            ) as response:
                if response.status == 200:
                    response_data = await response.json()

                    # Extract content from OpenAI response
                    if response_data.get("choices") and len(response_data["choices"]) > 0:
                        text_content = response_data["choices"][0]["message"]["content"]

                        try:
                            # Validate and normalize response using centralized validator
                            validated_response = validate_and_normalize_response(
                                text_content, provider="openai", correlation_id=correlation_id
                            )

                            # Convert to internal format
                            # Convert winner string to enum value
                            if validated_response.winner == "Essay A":
                                winner = EssayComparisonWinner.ESSAY_A
                            elif validated_response.winner == "Essay B":
                                winner = EssayComparisonWinner.ESSAY_B
                            else:
                                winner = EssayComparisonWinner.ERROR

                            # Convert confidence from 1-5 scale to 0-1 scale for internal model
                            confidence_normalized = (validated_response.confidence - 1.0) / 4.0

                            # Get token usage
                            usage = response_data.get("usage", {})
                            prompt_tokens = usage.get("prompt_tokens", 0)
                            completion_tokens = usage.get("completion_tokens", 0)
                            total_tokens = prompt_tokens + completion_tokens

                            # Create response model
                            response_model = LLMProviderResponse(
                                winner=winner,
                                justification=validated_response.justification,
                                confidence=confidence_normalized,
                                provider=LLMProviderType.OPENAI,
                                model=model,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                total_tokens=total_tokens,
                                raw_response=response_data,
                            )

                            return response_model

                        except (json.JSONDecodeError, ValueError, KeyError) as e:
                            error_msg = f"Failed to parse OpenAI response: {str(e)}"
                            logger.error(error_msg, extra={"response_text": text_content[:500]})
                            raise_parsing_error(
                                service="llm_provider_service",
                                operation="openai_api_request",
                                parse_target="json_response",
                                message=error_msg,
                                correlation_id=correlation_id,
                                details={"provider": "openai"},
                            )
                    else:
                        raise_external_service_error(
                            service="llm_provider_service",
                            operation="openai_api_request",
                            external_service="openai_api",
                            message="No choices in OpenAI response",
                            correlation_id=correlation_id,
                            details={"provider": "openai"},
                        )

                else:
                    error_text = await response.text()
                    error_msg = f"OpenAI API error: {response.status} - {error_text}"

                    # Raise for retryable status codes to trigger retry
                    if response.status in {429, 500, 502, 503, 504}:
                        response.raise_for_status()

                    # Handle specific HTTP errors with appropriate exceptions
                    if response.status == 429:
                        raise_rate_limit_error(
                            service="llm_provider_service",
                            operation="openai_api_request",
                            limit=0,  # Unknown limit from API
                            window_seconds=60,
                            message=f"Rate limit exceeded: {error_text}",
                            correlation_id=correlation_id,
                            details={"provider": "openai", "retry_after": 60},
                        )
                    elif response.status == 401:
                        raise_authentication_error(
                            service="llm_provider_service",
                            operation="openai_api_request",
                            message=f"Authentication failed: {error_text}",
                            correlation_id=correlation_id,
                            details={"provider": "openai"},
                        )
                    else:
                        raise_external_service_error(
                            service="llm_provider_service",
                            operation="openai_api_request",
                            external_service="openai_api",
                            message=error_msg,
                            correlation_id=correlation_id,
                            details={"provider": "openai", "status_code": response.status},
                        )

        except aiohttp.ClientResponseError:
            # Will be retried by retry manager
            raise
        except aiohttp.ClientError:
            # Connection errors, timeouts, etc.
            raise
        except Exception as e:
            # Unexpected errors
            error_msg = f"Unexpected error calling OpenAI API: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise_external_service_error(
                service="llm_provider_service",
                operation="openai_api_request",
                external_service="openai_api",
                message=error_msg,
                correlation_id=correlation_id,
                details={"provider": "openai"},
            )

    def _format_comparison_prompt(self, user_prompt: str, essay_a: str, essay_b: str) -> str:
        """Format the comparison prompt with essays.

        Args:
            user_prompt: The prompt template
            essay_a: First essay
            essay_b: Second essay

        Returns:
            Formatted prompt
        """
        # Simple formatting - could be enhanced with template engine
        formatted = user_prompt.replace("{essay_a}", essay_a).replace("{essay_b}", essay_b)

        # If no placeholders found, append essays
        if "{essay_a}" not in user_prompt and "{essay_b}" not in user_prompt:
            formatted = f"{user_prompt}\n\nEssay A:\n{essay_a}\n\nEssay B:\n{essay_b}"

        # Add JSON instruction
        formatted += "\n\nPlease respond with a valid JSON object."

        return formatted
