"""HTTP client for LLM Provider Service.

This implementation replaces direct LLM provider calls with HTTP requests
to the centralized LLM Provider Service.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import aiohttp
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.protocols import LLMProviderProtocol, RetryManagerProtocol

logger = create_service_logger("cj_assessment_service.llm_provider_service_client")


class LLMProviderServiceClient(LLMProviderProtocol):
    """HTTP client for centralized LLM Provider Service."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        settings: Settings,
        retry_manager: RetryManagerProtocol,
    ) -> None:
        """Initialize LLM Provider Service client.

        Args:
            session: HTTP session for making requests
            settings: Application settings containing service URL
            retry_manager: Retry manager for handling transient failures
        """
        self.session = session
        self.settings = settings
        self.retry_manager = retry_manager
        self.base_url = settings.LLM_PROVIDER_SERVICE_URL.rstrip("/")

    def _extract_essays_from_prompt(self, prompt: str) -> tuple[str, str, str] | None:
        """Extract base prompt and essays from formatted prompt.

        Args:
            prompt: Formatted prompt containing essays

        Returns:
            Tuple of (base_prompt, essay_a, essay_b) or None if extraction fails
        """
        try:
            # Find Essay A and Essay B sections
            lines = prompt.strip().split("\n")
            essay_a_start = essay_b_start = -1

            for i, line in enumerate(lines):
                if line.strip().startswith("Essay A"):
                    essay_a_start = i + 1
                elif line.strip().startswith("Essay B"):
                    essay_b_start = i + 1

            if essay_a_start == -1 or essay_b_start == -1:
                return None

            # Extract base prompt (everything before Essay A)
            base_prompt = "\n".join(lines[: essay_a_start - 1]).strip()

            # Extract Essay A (between Essay A and Essay B)
            essay_a = "\n".join(lines[essay_a_start : essay_b_start - 1]).strip()

            # Extract Essay B (after Essay B header)
            essay_b_lines = []
            for line in lines[essay_b_start:]:
                # Stop at the JSON instruction part if present
                if "Please respond with" in line or "Please provide your assessment" in line:
                    break
                essay_b_lines.append(line)
            essay_b = "\n".join(essay_b_lines).strip()

            return base_prompt, essay_a, essay_b

        except Exception as e:
            logger.error(f"Failed to extract essays from prompt: {e}")
            return None

    async def generate_comparison(
        self,
        user_prompt: str,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Generate comparison via LLM Provider Service.

        Args:
            user_prompt: The user prompt containing essay comparison request
            system_prompt_override: Optional system prompt override
            model_override: Optional model name override
            temperature_override: Optional temperature override (0.0-2.0)
            max_tokens_override: Optional max tokens override

        Returns:
            Tuple of (response_data, error_message)
        """
        # Extract essays from the formatted prompt
        extraction_result = self._extract_essays_from_prompt(user_prompt)
        if not extraction_result:
            logger.error("Could not extract essays from prompt")
            return None, "Invalid prompt format: Could not extract essays"

        base_prompt, essay_a, essay_b = extraction_result

        # Build request body for LLM Provider Service
        request_body = {
            "user_prompt": base_prompt,
            "essay_a": essay_a,
            "essay_b": essay_b,
            "llm_config_overrides": {
                # Provider will be determined by the configured default
                "provider_override": self.settings.DEFAULT_LLM_PROVIDER.lower(),
                "model_override": model_override or self.settings.DEFAULT_LLM_MODEL,
                "temperature_override": temperature_override
                or self.settings.DEFAULT_LLM_TEMPERATURE,
                "system_prompt_override": system_prompt_override,
                "max_tokens_override": max_tokens_override,
            },
            "correlation_id": str(uuid4()),
        }

        # Make HTTP request with retry logic
        url = f"{self.base_url}/comparison"

        async def make_request() -> tuple[dict[str, Any] | None, str | None]:
            try:
                async with self.session.post(
                    url,
                    json=request_body,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=60),  # 60 second timeout
                ) as response:
                    response_text = await response.text()

                    if response.status == 200:
                        try:
                            response_data = json.loads(response_text)

                            # Extract the comparison result
                            # LLM Provider Service already returns in correct format
                            result = {
                                "winner": response_data.get("winner"),
                                "justification": response_data.get("justification"),
                                "confidence": response_data.get("confidence"),
                            }

                            logger.info(
                                f"Successfully generated comparison via LLM Provider Service, "
                                f"provider: {response_data.get('provider')}, "
                                f"model: {response_data.get('model')}, "
                                f"cached: {response_data.get('cached', False)}"
                            )

                            return result, None

                        except json.JSONDecodeError as e:
                            error_msg = f"Failed to parse response JSON: {str(e)}"
                            logger.error(f"{error_msg}, response: {response_text[:200]}")
                            return None, error_msg

                    else:
                        # Handle error responses
                        try:
                            error_data = json.loads(response_text)
                            error_msg = error_data.get("error", f"HTTP {response.status}")
                            error_details = error_data.get("details", "")
                            full_error = (
                                f"{error_msg}: {error_details}" if error_details else error_msg
                            )
                        except json.JSONDecodeError:
                            full_error = f"HTTP {response.status}: {response_text[:200]}"

                        logger.error(f"LLM Provider Service error: {full_error}")
                        return None, full_error

            except aiohttp.ClientError as e:
                error_msg = f"HTTP request failed: {str(e)}"
                logger.error(error_msg)
                return None, error_msg
            except Exception as e:
                error_msg = f"Unexpected error calling LLM Provider Service: {str(e)}"
                logger.exception(error_msg)
                return None, error_msg

        # Use retry manager for resilience
        result, error = await self.retry_manager.with_retry(make_request)

        return result, error
