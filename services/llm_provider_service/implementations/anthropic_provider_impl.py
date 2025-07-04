"""Anthropic LLM provider implementation."""

import json
from typing import Tuple

import aiohttp
from huleedu_service_libs.logging_utils import create_service_logger

from common_core import LLMProviderType
from common_core.error_enums import ErrorCode
from services.llm_provider_service.config import Settings
from services.llm_provider_service.internal_models import LLMProviderError, LLMProviderResponse
from services.llm_provider_service.protocols import LLMProviderProtocol, LLMRetryManagerProtocol
from services.llm_provider_service.response_validator import (
    convert_to_internal_format,
    validate_and_normalize_response,
)

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
        self.api_key = settings.ANTHROPIC_API_KEY
        self.api_base = "https://api.anthropic.com/v1"

    async def generate_comparison(
        self,
        user_prompt: str,
        essay_a: str,
        essay_b: str,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> Tuple[LLMProviderResponse | None, LLMProviderError | None]:
        """Generate LLM comparison response.

        Args:
            user_prompt: The comparison prompt template
            essay_a: First essay to compare
            essay_b: Second essay to compare
            system_prompt_override: Optional system prompt override
            model_override: Optional model override
            temperature_override: Optional temperature override
            max_tokens_override: Optional max tokens override

        Returns:
            Tuple of (response_model, error_model)
        """
        if not self.api_key:
            from uuid import uuid4

            return None, LLMProviderError(
                error_type=ErrorCode.CONFIGURATION_ERROR,
                error_message="Anthropic API key not configured",
                provider=LLMProviderType.ANTHROPIC,
                correlation_id=uuid4(),
                is_retryable=False,
            )

        # Prepare the full prompt with essays
        full_prompt = self._format_comparison_prompt(user_prompt, essay_a, essay_b)

        # Use system prompt from override or default comparison prompt
        system_prompt = (
            system_prompt_override
            or """You are an expert essay evaluator tasked with comparing two student essays.

Your job is to:
1. Read both essays carefully
2. Determine which essay is better written based on clarity, structure, argument quality, and writing mechanics
3. Provide a brief justification for your choice (max 50 characters)
4. Rate your confidence in the decision

You will use the comparison_result tool to provide your analysis."""
        )

        # Execute with retry
        try:
            result = await self.retry_manager.with_retry(
                operation=self._make_api_request,
                operation_name="anthropic_api_request",
                system_prompt=system_prompt,
                user_prompt=full_prompt,
                model_override=model_override,
                temperature_override=temperature_override,
                max_tokens_override=max_tokens_override,
            )
            # Type assert since retry manager returns Any
            return result  # type: ignore
        except Exception as e:
            from uuid import uuid4

            return None, LLMProviderError(
                error_type=ErrorCode.EXTERNAL_SERVICE_ERROR,
                error_message=f"Anthropic API call failed: {str(e)}",
                provider=LLMProviderType.ANTHROPIC,
                correlation_id=uuid4(),
                is_retryable=True,
            )

    async def _make_api_request(
        self,
        system_prompt: str,
        user_prompt: str,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> Tuple[LLMProviderResponse | None, LLMProviderError | None]:
        """Make API request to Anthropic.

        Args:
            system_prompt: System prompt
            user_prompt: User prompt with essays
            model_override: Optional model override
            temperature_override: Optional temperature override
            max_tokens_override: Optional max tokens override

        Returns:
            Tuple of (response_model, error_model)
        """
        endpoint = f"{self.api_base}/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        # Determine model and parameters
        model = model_override or self.settings.ANTHROPIC_DEFAULT_MODEL
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
                        "justification": {"type": "string", "maxLength": 50, "description": "Brief explanation (max 50 chars)"},
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
                        from uuid import uuid4

                        return None, LLMProviderError(
                            error_type=ErrorCode.PARSING_ERROR,
                            error_message=f"Failed to parse Anthropic response: {str(e)}",
                            provider=LLMProviderType.ANTHROPIC,
                            correlation_id=uuid4(),
                            is_retryable=False,
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
                            validated_response, validation_error = validate_and_normalize_response(
                                tool_result
                            )

                            if validation_error:
                                error_msg = f"Response validation failed: {validation_error}"
                                logger.error(
                                    error_msg, extra={"tool_result": str(tool_result)[:500]}
                                )
                                from uuid import uuid4

                                return None, LLMProviderError(
                                    error_type=ErrorCode.EXTERNAL_SERVICE_ERROR,
                                    error_message=error_msg,
                                    provider=LLMProviderType.ANTHROPIC,
                                    correlation_id=uuid4(),
                                    is_retryable=False,
                                )

                            # Convert to internal format
                            assert validated_response is not None  # Type assertion for mypy
                            choice, reasoning, confidence = convert_to_internal_format(
                                validated_response
                            )

                            # Get token usage
                            usage = response_data.get("usage", {})
                            prompt_tokens = usage.get("input_tokens", 0)
                            completion_tokens = usage.get("output_tokens", 0)
                            total_tokens = prompt_tokens + completion_tokens

                            # Create response model
                            response_model = LLMProviderResponse(
                                choice=choice,
                                reasoning=reasoning,
                                confidence=confidence,
                                provider=LLMProviderType.ANTHROPIC,
                                model=model,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                total_tokens=total_tokens,
                                raw_response=response_data,
                            )

                            return response_model, None

                        except (ValueError, KeyError, TypeError) as e:
                            error_msg = f"Failed to parse Anthropic tool response: {str(e)}"
                            logger.error(error_msg, extra={"tool_result": str(tool_result)[:500]})
                            from uuid import uuid4

                            return None, LLMProviderError(
                                error_type=ErrorCode.EXTERNAL_SERVICE_ERROR,
                                error_message=error_msg,
                                provider=LLMProviderType.ANTHROPIC,
                                correlation_id=uuid4(),
                                is_retryable=False,
                            )
                    else:
                        # Log the full response for debugging
                        logger.error(
                            "No tool use found in Anthropic response",
                            extra={"response_data": str(response_data)[:1000]},
                        )
                        from uuid import uuid4

                        return None, LLMProviderError(
                            error_type=ErrorCode.EXTERNAL_SERVICE_ERROR,
                            error_message="No tool use found in Anthropic response",
                            provider=LLMProviderType.ANTHROPIC,
                            correlation_id=uuid4(),
                            is_retryable=False,
                        )

                else:
                    error_text = await response.text()
                    error_msg = f"Anthropic API error: {response.status} - {error_text}"

                    # Determine error type
                    if response.status == 429:
                        error_type = ErrorCode.RATE_LIMIT
                    elif response.status == 401:
                        error_type = ErrorCode.AUTHENTICATION_ERROR
                    elif response.status >= 500:
                        error_type = ErrorCode.EXTERNAL_SERVICE_ERROR
                    else:
                        error_type = ErrorCode.EXTERNAL_SERVICE_ERROR

                    # Raise for retryable status codes to trigger retry
                    if response.status in {429, 500, 502, 503, 504}:
                        response.raise_for_status()

                    from uuid import uuid4

                    return None, LLMProviderError(
                        error_type=error_type,
                        error_message=error_msg,
                        provider=LLMProviderType.ANTHROPIC,
                        correlation_id=uuid4(),
                        retry_after=60 if response.status == 429 else None,
                        is_retryable=response.status in {429, 500, 502, 503, 504},
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
            from uuid import uuid4

            return None, LLMProviderError(
                error_type=ErrorCode.EXTERNAL_SERVICE_ERROR,
                error_message=error_msg,
                provider=LLMProviderType.ANTHROPIC,
                correlation_id=uuid4(),
                is_retryable=True,
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

        return formatted
