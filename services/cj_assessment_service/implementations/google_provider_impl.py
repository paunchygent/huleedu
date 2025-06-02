"""Google (Gemini) LLM provider implementation."""

from __future__ import annotations

import json
from typing import Any, cast

import aiohttp
from config import Settings
from huleedu_service_libs.logging_utils import create_service_logger
from models_api import LLMAssessmentResponseSchema
from protocols import LLMProviderProtocol, RetryManagerProtocol
from pydantic import ValidationError

logger = create_service_logger("cj_assessment_service.google_provider_impl")


class GoogleProviderImpl(LLMProviderProtocol):
    """Google LLM provider implementation."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        settings: Settings,
        retry_manager: RetryManagerProtocol,
    ) -> None:
        """Initialize Google provider."""
        self.session = session
        self.settings = settings
        self.retry_manager = retry_manager
        self.provider_name = "Google"
        self.api_key = getattr(settings, "google_api_key", None)
        provider_config = settings.llm_providers.get("google")
        self.api_base = provider_config.api_base if provider_config else None
        self.model_name = self._get_model_name()

    def _get_model_name(self) -> str:
        """Get model name from settings."""
        model_name = self.settings.comparison_model
        if "/" in model_name:
            parts = model_name.split("/", 1)
            if len(parts) == 2 and parts[0].lower() == "google":
                model_name = parts[1]
        return str(model_name)

    async def generate_comparison(
        self,
        user_prompt: str,
        system_prompt_override: str | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Generate a comparison by calling the Google provider."""
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
        """Make API request to Google provider."""
        if not self.api_base:
            raise ValueError(f"{self.provider_name} API base URL not configured.")

        endpoint = f"{self.api_base.rstrip('/')}/v1beta/models/{self.model_name}:generateContent"
        headers = {
            "Content-Type": "application/json",
        }

        # Add API key to URL parameters for Google API
        url_with_key = f"{endpoint}?key={self.api_key}"

        provider_cfg = self.settings.llm_providers.get("google")
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

        # Combine system and user prompts for Gemini
        combined_prompt = f"{system_prompt}\n\n{user_prompt}"

        payload = {
            "contents": [{"parts": [{"text": combined_prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            },
        }

        # Execute HTTP request
        timeout_config = aiohttp.ClientTimeout(
            total=self.settings.llm_request_timeout_seconds,
        )

        try:
            async with self.session.post(
                url_with_key, headers=headers, json=payload, timeout=timeout_config
            ) as response:
                if response.status == 200:
                    response_data = await response.json()
                    # Extract text content from Google response
                    try:
                        text_content = response_data["candidates"][0]["content"]["parts"][0]["text"]
                        if isinstance(text_content, str):
                            # Validate JSON
                            try:
                                parsed_content = json.loads(text_content)
                                validated_data = LLMAssessmentResponseSchema(**parsed_content)
                                # Type cast to satisfy mypy
                                response_dict: dict[str, Any] = validated_data.model_dump()
                                return response_dict, None
                            except (json.JSONDecodeError, ValidationError) as e:
                                return (
                                    None,
                                    f"Invalid response structure from {self.provider_name}: {e!s}",
                                )
                    except (KeyError, IndexError, TypeError):
                        pass

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
