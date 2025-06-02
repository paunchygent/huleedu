"""OpenAI LLM provider implementation.

Extracted from llm_caller.py OpenAIProvider class to follow clean architecture
with protocol-based dependency injection.
"""

from __future__ import annotations

import json
from typing import Any, cast

import aiohttp
from config import Settings
from huleedu_service_libs.logging_utils import create_service_logger
from models_api import LLMAssessmentResponseSchema
from protocols import LLMProviderProtocol, RetryManagerProtocol
from pydantic import ValidationError

logger = create_service_logger("cj_assessment_service.openai_provider_impl")


class OpenAIProviderImpl(LLMProviderProtocol):
    """OpenAI LLM provider implementation.

    Handles request formatting and response parsing for OpenAI-based LLMs.
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
        self.provider_name = "OpenAI"
        self.api_key = self._get_api_key()
        self.api_base = self._get_api_base()
        self.model_name = self._get_model_name()

        if not self.api_key:
            logger.warning(
                f"API key for {self.provider_name} not found. Operations may fail.",
            )

    def _get_api_key(self) -> str | None:
        """Get API key from settings."""
        api_key_name = f"{self.provider_name.lower()}_api_key"
        api_key = getattr(self.settings, api_key_name, None)
        return str(api_key) if api_key is not None else None

    def _get_api_base(self) -> str | None:
        """Get API base URL from settings."""
        provider_config = self.settings.llm_providers.get(self.provider_name.lower())
        if provider_config and provider_config.api_base:
            return str(provider_config.api_base)
        logger.warning(
            f"API base URL for {self.provider_name} not found in llm_providers config.",
        )
        return None

    def _get_model_name(self) -> str:
        """Get model name from settings."""
        model_name = self.settings.comparison_model

        # Strip provider prefix if model name includes it
        if "/" in model_name:
            parts = model_name.split("/", 1)
            if len(parts) == 2 and parts[0].lower() == self.provider_name.lower():
                model_name = parts[1]
        return str(model_name)

    def _prepare_request_details(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        """Prepare OpenAI-specific request details."""
        if not self.api_base:
            raise ValueError(f"{self.provider_name} API base URL not configured.")
        if not self.api_key:
            raise ValueError(f"{self.provider_name} API key not configured.")

        endpoint = self.api_base.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Use provider-specific config if available, else fallback
        provider_cfg = self.settings.llm_providers.get("openai")
        max_tokens = (
            provider_cfg.max_tokens
            if provider_cfg and provider_cfg.max_tokens is not None
            else self.settings.max_tokens_response
        )
        temperature = (
            provider_cfg.temperature
            if provider_cfg and provider_cfg.temperature is not None
            else self.settings.temperature
        )

        payload = {
            "model": self.model_name,
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
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Make API request to OpenAI provider."""
        endpoint, headers, payload = self._prepare_request_details(system_prompt, user_prompt)

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
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Generate a comparison by calling the OpenAI provider."""
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
            ),
            provider_name=self.provider_name,
        )
        return cast(tuple[dict[str, Any] | None, str | None], result)
