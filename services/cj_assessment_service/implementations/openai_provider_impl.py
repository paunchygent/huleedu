"""OpenAI LLM provider implementation.

Extracted from llm_caller.py OpenAIProvider class to follow clean architecture
with protocol-based dependency injection.
"""

from __future__ import annotations

import json
import os
from typing import Any, cast

import aiohttp
from config import Settings
from huleedu_service_libs.logging_utils import create_service_logger
from models_api import LLMAssessmentResponseSchema
from pydantic import ValidationError

from services.cj_assessment_service.protocols import LLMProviderProtocol, RetryManagerProtocol

logger = create_service_logger("cj_assessment_service.openai_provider_impl")


class OpenAIProviderImpl(LLMProviderProtocol):
    """OpenAI LLM provider implementation.

    Handles request formatting and response parsing for OpenAI-based LLMs.
    Uses structured LLM provider configuration.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        settings: Settings,
        retry_manager: RetryManagerProtocol,
    ) -> None:
        """Initialize OpenAI provider with dependencies.

        Args:
            session: HTTP client session for API requests.
            settings: Application settings.
            retry_manager: Retry logic implementation.
        """
        self.session = session
        self.settings = settings
        self.retry_manager = retry_manager
        self.provider_name = "openai"

        # Get provider-specific configuration
        self.provider_config = self.settings.LLM_PROVIDERS_CONFIG.get(self.provider_name)
        if not self.provider_config:
            raise ValueError(f"No configuration found for provider '{self.provider_name}'")

        self.api_key = self._get_api_key()
        self.api_base = self.provider_config.api_base
        self.model_name = self._get_model_name()

        if not self.api_key:
            logger.warning(
                f"API key for {self.provider_name} not found. Operations may fail.",
            )

    def _get_api_key(self) -> str | None:
        """Get API key from environment using structured configuration."""
        if not self.provider_config:
            return None

        # Get API key from environment variable specified in config
        api_key_env_var = self.provider_config.api_key_env_var
        api_key = os.getenv(api_key_env_var)

        # Fallback to legacy settings for backward compatibility
        if not api_key:
            api_key = getattr(self.settings, "OPENAI_API_KEY", None)

        return api_key

    def _get_model_name(self, model_override: str | None = None) -> str:
        """Get model name from structured configuration with optional override."""
        # Highest priority: runtime override
        if model_override:
            return model_override

        if not self.provider_config:
            return self.settings.DEFAULT_LLM_MODEL

        # Use provider's default model unless overridden
        return self.provider_config.default_model

    def _prepare_request_details(
        self,
        system_prompt: str,
        user_prompt: str,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        """Prepare OpenAI-specific request details with optional overrides."""
        if not self.api_base:
            raise ValueError(f"{self.provider_name} API base URL not configured.")
        if not self.api_key:
            raise ValueError(f"{self.provider_name} API key not configured.")

        endpoint = self.api_base.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Apply fallback chain: runtime_override → provider_default → global_default
        model_name = self._get_model_name(model_override)

        # Temperature: runtime override → provider config → global setting
        temperature = temperature_override
        if temperature is None:
            temperature = (
                self.provider_config.temperature
                if self.provider_config and self.provider_config.temperature is not None
                else self.settings.TEMPERATURE
            )

        # Max tokens: runtime override → provider config → global setting
        max_tokens = max_tokens_override
        if max_tokens is None:
            max_tokens = (
                self.provider_config.max_tokens
                if self.provider_config and self.provider_config.max_tokens is not None
                else self.settings.MAX_TOKENS_RESPONSE
            )

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},  # Request JSON mode
        }
        return endpoint, headers, payload

    def _extract_assessment_json_string(self, response_data: dict[str, Any]) -> str:
        """Extract assessment JSON string from OpenAI response."""
        try:
            content = response_data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(
                f"Malformed response structure in {self.provider_name}: {e}",
            ) from e
        if not isinstance(content, str):
            raise ValueError(
                f"Content in {self.provider_name} response is not a string: {content!r}",
            )
        return content

    def _validate_assessment_json_string(
        self,
        assessment_json_string: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Parse and validate the assessment JSON string."""
        try:
            parsed_content = json.loads(assessment_json_string)
            validated_data = LLMAssessmentResponseSchema(**parsed_content)
            # Type cast to satisfy mypy - model_dump() returns dict[str, Any]
            response_dict: dict[str, Any] = validated_data.model_dump()
            return response_dict, None
        except json.JSONDecodeError as e:
            logger.error(
                f"Error decoding JSON content from {self.provider_name}: {e}. "
                f"Content string: '{assessment_json_string[:100]}...'",
            )
            return None, f"Failed to parse LLM provider JSON response: {e!s}"
        except ValidationError as e:
            parsed_content_for_log = "N/A (JSON was parsable but schema validation failed)"
            try:
                parsed_content_for_log = json.loads(assessment_json_string)
            except json.JSONDecodeError:
                pass
            logger.error(
                f"Validation error for {self.provider_name} response: {e}. "
                f"Parsed: {parsed_content_for_log}",
            )
            return None, f"Invalid data from {self.provider_name} after parsing: {e!s}"

    async def _execute_http_request(
        self,
        url: str,
        headers: dict[str, str],
        json_payload: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Execute HTTP request to OpenAI API."""
        timeout_config = aiohttp.ClientTimeout(
            total=self.settings.llm_request_timeout_seconds,
        )
        try:
            async with self.session.post(
                url,
                headers=headers,
                json=json_payload,
                timeout=timeout_config,
            ) as response:
                if response.status == 200:
                    try:
                        return await response.json(), None
                    except json.JSONDecodeError as e:
                        error_text = await response.text()
                        logger.error(
                            f"{self.provider_name} API success status (200) but "
                            f"failed to parse JSON: {e}. Response text: "
                            f"{error_text[:200]}"
                        )
                        return (
                            None,
                            f"API returned 200 OK but content was not valid JSON: {e!s}",
                        )

                # For non-200 responses
                error_text = await response.text()
                retryable_status_codes = {429, 500, 502, 503, 504}
                if response.status in retryable_status_codes:
                    logger.warning(
                        f"{self.provider_name} API error ({response.status}) - raising for retry: "
                        f"{error_text[:200]}"
                    )
                    response.raise_for_status()
                    return None, "Error: Should have been retried"

                # Non-retryable error
                logger.error(
                    f"{self.provider_name} API error ({response.status}) - not retryable: "
                    f"{error_text[:200]}"
                )
                return (
                    None,
                    f"API error ({response.status}): {error_text[:200]}...",
                )

        except (TimeoutError, aiohttp.ClientResponseError, aiohttp.ClientError):
            # Re-raise for retry manager to handle
            raise
        except Exception as e:
            logger.error(
                f"Unexpected HTTP request error for {self.provider_name}: {e}",
                exc_info=True,
            )
            return None, f"Unexpected request error: {e!s}"

    async def _make_provider_api_request(
        self,
        system_prompt: str,
        user_prompt: str,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Make API request to OpenAI provider with optional overrides."""
        endpoint, headers, payload = self._prepare_request_details(
            system_prompt,
            user_prompt,
            model_override=model_override,
            temperature_override=temperature_override,
            max_tokens_override=max_tokens_override,
        )

        # Execute HTTP request
        response_data, error_message = await self._execute_http_request(endpoint, headers, payload)

        if error_message:
            return None, error_message

        if response_data:
            # Extract assessment JSON string from response
            try:
                assessment_json_string = self._extract_assessment_json_string(response_data)
                return self._validate_assessment_json_string(assessment_json_string)
            except ValueError as e:
                logger.error(f"Error extracting assessment from {self.provider_name} response: {e}")
                return None, str(e)

        return None, f"No response data from {self.provider_name}"

    async def generate_comparison(
        self,
        user_prompt: str,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Generate a comparison by calling the OpenAI provider with optional overrides."""
        if not self.api_key:
            return None, f"{self.provider_name} API key not configured."

        final_system_prompt = system_prompt_override or self.settings.system_prompt
        if not final_system_prompt:
            final_system_prompt = ""

        # Use cast to help mypy understand the return type from retry_manager
        result = await self.retry_manager.call_with_retry(
            api_request_func=lambda: self._make_provider_api_request(
                final_system_prompt,
                user_prompt,
                model_override=model_override,
                temperature_override=temperature_override,
                max_tokens_override=max_tokens_override,
            ),
            provider_name=self.provider_name,
        )
        return cast(tuple[dict[str, Any] | None, str | None], result)
