"""OpenRouter LLM provider implementation."""

import json
import time
from typing import Dict, Optional
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

logger = create_service_logger("llm_provider_service.openrouter_provider")


class OpenRouterProviderImpl(LLMProviderProtocol):
    """OpenRouter LLM provider implementation."""

    # Class-level cache for model capabilities
    _model_cache: Dict[str, Dict] = {}
    _cache_ttl_seconds = 3600  # 1 hour TTL
    _cache_max_size = 100

    def __init__(
        self,
        session: aiohttp.ClientSession,
        settings: Settings,
        retry_manager: LLMRetryManagerProtocol,
    ):
        """Initialize OpenRouter provider.

        Args:
            session: HTTP client session
            settings: Service settings
            retry_manager: Retry manager for resilient requests
        """
        self.session = session
        self.settings = settings
        self.retry_manager = retry_manager
        self.api_key = settings.OPENROUTER_API_KEY.get_secret_value()
        self.api_base = settings.OPENROUTER_BASE_URL

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
                config_key="OPENROUTER_API_KEY",
                message="OpenRouter API key not configured",
                correlation_id=correlation_id,
                details={"provider": "openrouter"},
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
                operation_name="openrouter_api_request",
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
                operation="openrouter_api_request",
                external_service="openrouter_api",
                message=f"OpenRouter API call failed: {str(e)}",
                correlation_id=correlation_id,
                details={"provider": "openrouter"},
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
        """Make API request to OpenRouter.

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
            HuleEduError: On API request failure
        """
        endpoint = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://huleedu.com",  # OpenRouter requires this
            "X-Title": "HuleEdu LLM Provider Service",  # Optional but recommended
        }

        # Determine model and parameters
        model = model_override or self.settings.OPENROUTER_DEFAULT_MODEL
        temperature = (
            temperature_override
            if temperature_override is not None
            else self.settings.LLM_DEFAULT_TEMPERATURE
        )
        max_tokens = max_tokens_override or self.settings.LLM_DEFAULT_MAX_TOKENS

        # Check model capabilities from cache or fetch if needed
        model_info = self._get_cached_model_info(model)
        if model_info is None:
            # Try to fetch model info (don't block on failure)
            try:
                model_info = await self._fetch_model_info(model)
            except Exception as e:
                logger.debug(f"Failed to fetch model info for {model}: {e}")
                model_info = None

        if model_info and not model_info.get("supports_json", True):
            logger.warning(f"Model {model} may not support JSON response format")

        # Adjust max_tokens based on cached model limits if available
        if model_info and "context_length" in model_info:
            context_limit = model_info["context_length"]
            estimated_prompt_tokens = (
                len(f"{system_prompt} {user_prompt}".split()) * 1.3
            )  # Rough estimate
            safe_max_tokens = min(max_tokens, int(context_limit - estimated_prompt_tokens))
            if safe_max_tokens != max_tokens:
                max_tokens = max(safe_max_tokens, 100)  # Ensure minimum viable response

        # OpenRouter uses OpenAI-compatible API with JSON mode
        # Note: Only JSON-capable models should be configured for CJ Assessment
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": {"type": "json_object"},  # Request JSON response
        }

        try:
            async with self.session.post(
                endpoint,
                headers=headers,
                json=payload,
            ) as response:
                if response.status == 200:
                    response_data = await response.json()

                    # Extract content from OpenRouter response (OpenAI format)
                    if response_data.get("choices") and len(response_data["choices"]) > 0:
                        text_content = response_data["choices"][0]["message"]["content"]

                        try:
                            # Validate and normalize response using centralized validator
                            validated_response = validate_and_normalize_response(
                                text_content, provider="openrouter", correlation_id=correlation_id
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
                                provider=LLMProviderType.OPENROUTER,
                                model=model,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                total_tokens=total_tokens,
                                raw_response=response_data,
                            )

                            return response_model

                        except (json.JSONDecodeError, ValueError, KeyError) as e:
                            error_msg = f"Failed to parse OpenRouter response: {str(e)}"
                            logger.error(error_msg, extra={"response_text": text_content[:500]})
                            raise_parsing_error(
                                service="llm_provider_service",
                                operation="openrouter_response_parsing",
                                parse_target="openrouter_response",
                                message=error_msg,
                                correlation_id=correlation_id,
                                details={
                                    "provider": "openrouter",
                                    "response_preview": text_content[:100],
                                },
                            )
                    else:
                        raise_external_service_error(
                            service="llm_provider_service",
                            operation="openrouter_response_parsing",
                            external_service="openrouter_api",
                            message="No choices in OpenRouter response",
                            correlation_id=correlation_id,
                            details={"provider": "openrouter"},
                        )

                else:
                    error_text = await response.text()
                    error_msg = f"OpenRouter API error: {response.status} - {error_text}"

                    # Raise for retryable status codes to trigger retry
                    if response.status in {429, 500, 502, 503, 504}:
                        response.raise_for_status()

                    # Determine error type and raise appropriate exception
                    if response.status == 429:
                        raise_rate_limit_error(
                            service="llm_provider_service",
                            operation="openrouter_api_request",
                            limit=1000,  # Default reasonable limit
                            window_seconds=60,  # 1 minute window
                            message=error_msg,
                            correlation_id=correlation_id,
                            details={"provider": "openrouter", "retry_after": 60},
                        )
                    elif response.status == 401 or response.status == 403:
                        raise_authentication_error(
                            service="llm_provider_service",
                            operation="openrouter_api_request",
                            message=error_msg,
                            correlation_id=correlation_id,
                            details={"provider": "openrouter"},
                        )
                    else:
                        raise_external_service_error(
                            service="llm_provider_service",
                            operation="openrouter_api_request",
                            external_service="openrouter_api",
                            message=error_msg,
                            correlation_id=correlation_id,
                            details={"provider": "openrouter", "status_code": response.status},
                        )

        except aiohttp.ClientResponseError:
            # Will be retried by retry manager
            raise
        except aiohttp.ClientError:
            # Connection errors, timeouts, etc.
            raise
        except Exception as e:
            # Unexpected errors
            error_msg = f"Unexpected error calling OpenRouter API: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise_external_service_error(
                service="llm_provider_service",
                operation="openrouter_api_request",
                external_service="openrouter_api",
                message=error_msg,
                correlation_id=correlation_id,
                details={"provider": "openrouter"},
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

    def _get_cached_model_info(self, model: str) -> Optional[Dict]:
        """Get cached model information.

        Args:
            model: Model identifier

        Returns:
            Cached model info or None if not cached/expired
        """
        if model not in self._model_cache:
            return None

        cache_entry = self._model_cache[model]
        cache_time = cache_entry.get("cached_at", 0)

        # Check if cache entry is expired
        if time.time() - cache_time > self._cache_ttl_seconds:
            del self._model_cache[model]
            return None

        return cache_entry.get("info")

    def _cache_model_info(self, model: str, model_info: Dict) -> None:
        """Cache model information with TTL.

        Args:
            model: Model identifier
            model_info: Model capability information
        """
        # Implement simple LRU by removing oldest entries if cache is full
        if len(self._model_cache) >= self._cache_max_size:
            # Remove oldest entry (simple approach)
            oldest_model = min(
                self._model_cache.keys(), key=lambda k: self._model_cache[k].get("cached_at", 0)
            )
            del self._model_cache[oldest_model]

        self._model_cache[model] = {"info": model_info, "cached_at": time.time()}

        logger.debug(f"Cached model info for {model}, cache size: {len(self._model_cache)}")

    async def _fetch_model_info(self, model: str) -> Optional[Dict]:
        """Fetch model information from OpenRouter API.

        Args:
            model: Model identifier

        Returns:
            Model information or None if fetch fails
        """
        try:
            models_endpoint = f"{self.api_base}/models"
            headers = {"Authorization": f"Bearer {self.api_key}"}

            async with self.session.get(models_endpoint, headers=headers) as response:
                if response.status == 200:
                    models_data = await response.json()

                    # Find the specific model in the response
                    for model_data in models_data.get("data", []):
                        if model_data.get("id") == model:
                            model_info = {
                                "context_length": model_data.get("context_length", 4096),
                                "supports_json": "json" in model_data.get("name", "").lower(),
                                "pricing": {
                                    "prompt": model_data.get("pricing", {}).get("prompt", 0),
                                    "completion": model_data.get("pricing", {}).get(
                                        "completion", 0
                                    ),
                                },
                            }

                            # Cache the information
                            self._cache_model_info(model, model_info)
                            return model_info

                    logger.warning(f"Model {model} not found in OpenRouter models list")
                    return None
                else:
                    logger.warning(f"Failed to fetch models from OpenRouter: {response.status}")
                    return None

        except Exception as e:
            logger.error(f"Error fetching model info for {model}: {e}")
            return None
