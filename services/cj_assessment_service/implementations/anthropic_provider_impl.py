"""Anthropic LLM provider implementation."""

from __future__ import annotations

import json
import os
from typing import Any, cast

import aiohttp
from config import Settings
from models_api import LLMAssessmentResponseSchema
from protocols import LLMProviderProtocol, RetryManagerProtocol
from pydantic import ValidationError


class AnthropicProviderImpl(LLMProviderProtocol):
    """Anthropic LLM provider implementation.

    Uses structured LLM provider configuration.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        settings: Settings,
        retry_manager: RetryManagerProtocol,
    ) -> None:
        """Initialize Anthropic provider."""
        self.session = session
        self.settings = settings
        self.retry_manager = retry_manager
        self.provider_name = "anthropic"

        # Get provider-specific configuration
        self.provider_config = self.settings.LLM_PROVIDERS_CONFIG.get(self.provider_name)
        if not self.provider_config:
            raise ValueError(f"No configuration found for provider '{self.provider_name}'")

        self.api_key = self._get_api_key()
        self.api_base = self.provider_config.api_base
        self.model_name = self._get_model_name()

    def _get_api_key(self) -> str | None:
        """Get API key from environment using structured configuration."""
        if not self.provider_config:
            return None

        # Get API key from environment variable specified in config
        api_key_env_var = self.provider_config.api_key_env_var
        api_key = os.getenv(api_key_env_var)

        # Fallback to legacy settings for backward compatibility
        if not api_key:
            api_key = getattr(self.settings, 'ANTHROPIC_API_KEY', None)

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

    async def generate_comparison(
        self,
        user_prompt: str,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Generate a comparison by calling the Anthropic provider with optional overrides."""
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

    async def _make_provider_api_request(
        self,
        system_prompt: str,
        user_prompt: str,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Make API request to Anthropic provider with optional overrides."""
        if not self.api_base:
            raise ValueError(f"{self.provider_name} API base URL not configured.")

        endpoint = self.api_base.rstrip("/") + "/messages"
        headers = {
            "x-api-key": str(self.api_key),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
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
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        # Execute HTTP request
        timeout_config = aiohttp.ClientTimeout(
            total=self.settings.LLM_REQUEST_TIMEOUT_SECONDS,
        )

        try:
            async with self.session.post(
                endpoint, headers=headers, json=payload, timeout=timeout_config
            ) as response:
                if response.status == 200:
                    response_data = await response.json()
                    # Extract text content from Anthropic response
                    if isinstance(response_data.get("content"), list):
                        for block in response_data["content"]:
                            if block.get("type") == "text":
                                text_content = block.get("text")
                                if isinstance(text_content, str):
                                    # Validate JSON
                                    try:
                                        parsed_content = json.loads(text_content)
                                        validated_data = LLMAssessmentResponseSchema(
                                            **parsed_content
                                        )
                                        # Type cast to satisfy mypy - model_dump()
                                        # returns dict[str, Any]
                                        response_dict: dict[str, Any] = validated_data.model_dump()
                                        return response_dict, None
                                    except (json.JSONDecodeError, ValidationError) as e:
                                        return (
                                            None,
                                            (
                                                f"Invalid response structure from "
                                                f"{self.provider_name}: {e!s}"
                                            ),
                                        )

                    return None, f"Invalid response structure from {self.provider_name}"
                else:
                    error_text = await response.text()
                    if response.status in {429, 500, 502, 503, 504}:
                        response.raise_for_status()  # Will be retried
                    return None, f"API error: {response.status} - {error_text}"

        except (TimeoutError, aiohttp.ClientResponseError, aiohttp.ClientError):
            raise  # Re-raise for retry manager
        except Exception as e:
            return None, f"Unexpected HTTP request error: {e!s}"
