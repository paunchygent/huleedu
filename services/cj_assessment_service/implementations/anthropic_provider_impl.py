"""Anthropic LLM provider implementation."""

from __future__ import annotations

import json
from typing import Any, cast

import aiohttp
from config import Settings
from models_api import LLMAssessmentResponseSchema
from protocols import LLMProviderProtocol, RetryManagerProtocol
from pydantic import ValidationError


class AnthropicProviderImpl(LLMProviderProtocol):
    """Anthropic LLM provider implementation."""

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
        self.provider_name = "Anthropic"
        self.api_key = getattr(settings, "anthropic_api_key", None)
        provider_config = settings.llm_providers.get("anthropic")
        self.api_base = provider_config.api_base if provider_config else None
        self.model_name = self._get_model_name()

    def _get_model_name(self) -> str:
        """Get model name from settings."""
        model_name = self.settings.comparison_model
        if "/" in model_name:
            parts = model_name.split("/", 1)
            if len(parts) == 2 and parts[0].lower() == "anthropic":
                model_name = parts[1]
        return str(model_name)

    async def generate_comparison(
        self,
        user_prompt: str,
        system_prompt_override: str | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Generate a comparison by calling the Anthropic provider."""
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

    async def _make_provider_api_request(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Make API request to Anthropic provider."""
        if not self.api_base:
            raise ValueError(f"{self.provider_name} API base URL not configured.")

        endpoint = self.api_base.rstrip("/") + "/messages"
        headers = {
            "x-api-key": str(self.api_key),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        provider_cfg = self.settings.llm_providers.get("anthropic")
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
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        # Execute HTTP request
        timeout_config = aiohttp.ClientTimeout(
            total=self.settings.llm_request_timeout_seconds,
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
