"""HTTP client for LLM Provider Service.

This implementation replaces direct LLM provider calls with HTTP requests
to the centralized LLM Provider Service.
"""

from __future__ import annotations

import asyncio
import json
import time
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
                if line.strip().startswith("Essay A") and ":" in line:
                    essay_a_start = i + 1
                elif line.strip().startswith("Essay B") and ":" in line:
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
        provider_override: str | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Generate comparison via LLM Provider Service.

        Handles both immediate (200) and queued (202) responses from the LLM Provider Service.
        For queued responses, implements polling with exponential backoff.

        Args:
            user_prompt: The user prompt containing essay comparison request
            system_prompt_override: Optional system prompt override
            model_override: Optional model name override
            temperature_override: Optional temperature override (0.0-2.0)
            max_tokens_override: Optional max tokens override
            provider_override: Optional provider name override

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
                "provider_override": provider_override or self.settings.DEFAULT_LLM_PROVIDER.value,
                "model_override": model_override or self.settings.DEFAULT_LLM_MODEL,
                "temperature_override": temperature_override
                or self.settings.DEFAULT_LLM_TEMPERATURE,
                "system_prompt_override": system_prompt_override,
                "max_tokens_override": max_tokens_override,
            },
            "correlation_id": str(uuid4()),
        }

        # Make initial HTTP request with retry logic
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
                        # Immediate response - handle as before
                        return await self._handle_immediate_response(response_text)

                    elif response.status == 202:
                        # Queued response - start polling
                        return await self._handle_queued_response(response_text)

                    else:
                        # Handle error responses
                        return await self._handle_error_response(response.status, response_text)

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

    async def _handle_immediate_response(
        self, response_text: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Handle immediate (200) response from LLM Provider Service.

        Args:
            response_text: Raw response text from the HTTP response

        Returns:
            Tuple of (response_data, error_message)
        """
        try:
            response_data = json.loads(response_text)

            # Extract the comparison result and preserve 1-5 confidence scale
            # LLM Provider Service returns 1-5 scale, keep as-is for CJ Assessment
            confidence = response_data.get("confidence", 3.0)

            result = {
                "winner": response_data.get("winner"),
                "justification": response_data.get("justification"),
                "confidence": confidence,
            }

            logger.info(
                f"Successfully generated comparison via LLM Provider Service (immediate), "
                f"provider: {response_data.get('provider')}, "
                f"model: {response_data.get('model')}, "
                f"response_time: {response_data.get('response_time_ms', 'N/A')}ms"
            )

            return result, None

        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse immediate response JSON: {str(e)}"
            logger.error(f"{error_msg}, response: {response_text[:200]}")
            return None, error_msg

    async def _handle_queued_response(
        self, response_text: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Handle queued (202) response from LLM Provider Service.

        Args:
            response_text: Raw response text from the HTTP response

        Returns:
            Tuple of (response_data, error_message)
        """
        try:
            queue_response = json.loads(response_text)
            queue_id = queue_response.get("queue_id")

            if not queue_id:
                return None, "Queue response missing queue_id"

            logger.info(
                f"Request queued for processing, queue_id: {queue_id}, "
                f"estimated_wait: {queue_response.get('estimated_wait_minutes', 'N/A')} minutes"
            )

            # Check if polling is disabled
            if not self.settings.LLM_QUEUE_POLLING_ENABLED:
                return None, "Request queued but polling is disabled"

            # Start polling for results
            return await self._poll_for_results(queue_id)

        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse queued response JSON: {str(e)}"
            logger.error(f"{error_msg}, response: {response_text[:200]}")
            return None, error_msg

    async def _handle_error_response(
        self, status_code: int, response_text: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Handle error responses from LLM Provider Service.

        Args:
            status_code: HTTP status code
            response_text: Raw response text from the HTTP response

        Returns:
            Tuple of (response_data, error_message)
        """
        try:
            error_data = json.loads(response_text)
            error_msg = error_data.get("error", f"HTTP {status_code}")
            error_details = error_data.get("details", "")
            full_error = f"{error_msg}: {error_details}" if error_details else error_msg
        except json.JSONDecodeError:
            full_error = f"HTTP {status_code}: {response_text[:200]}"

        logger.error(f"LLM Provider Service error: {full_error}")
        return None, full_error

    async def _poll_for_results(self, queue_id: str) -> tuple[dict[str, Any] | None, str | None]:
        """Poll for results from the queue using exponential backoff.

        Args:
            queue_id: Queue identifier to poll for results

        Returns:
            Tuple of (response_data, error_message)
        """
        start_time = time.time()
        attempt = 0
        delay = self.settings.LLM_QUEUE_POLLING_INITIAL_DELAY_SECONDS

        logger.info(f"Starting queue polling for queue_id: {queue_id}")

        while attempt < self.settings.LLM_QUEUE_POLLING_MAX_ATTEMPTS:
            # Check total timeout
            timeout_seconds = self.settings.LLM_QUEUE_TOTAL_TIMEOUT_SECONDS
            if time.time() - start_time > timeout_seconds:
                logger.error(f"Queue polling timed out after {timeout_seconds} seconds")
                return None, "Queue processing timed out"

            # Wait before polling (except first attempt)
            if attempt > 0:
                logger.debug(f"Waiting {delay:.1f}s before next poll attempt {attempt + 1}")
                await asyncio.sleep(delay)

            # Check queue status
            status_result = await self._check_queue_status(queue_id)
            if status_result is None:
                # Error occurred, increment attempt and continue
                attempt += 1
                delay = min(
                    delay * self.settings.LLM_QUEUE_POLLING_EXPONENTIAL_BASE,
                    self.settings.LLM_QUEUE_POLLING_MAX_DELAY_SECONDS,
                )
                continue

            status = status_result.get("status")

            if status == "completed":
                # Result should be available, retrieve it
                return await self._retrieve_queue_result(queue_id)

            elif status == "failed":
                error_msg = status_result.get("error_message", "Queue processing failed")
                logger.error(f"Queue processing failed: {error_msg}")
                return None, f"Queue processing failed: {error_msg}"

            elif status == "expired":
                logger.error(f"Queue request expired for queue_id: {queue_id}")
                return None, "Queue request expired"

            elif status in ["queued", "processing"]:
                # Continue polling
                logger.debug(f"Queue status: {status}, continuing to poll")
                attempt += 1
                delay = min(
                    delay * self.settings.LLM_QUEUE_POLLING_EXPONENTIAL_BASE,
                    self.settings.LLM_QUEUE_POLLING_MAX_DELAY_SECONDS,
                )
                continue

            else:
                logger.warning(f"Unknown queue status: {status}")
                attempt += 1
                delay = min(
                    delay * self.settings.LLM_QUEUE_POLLING_EXPONENTIAL_BASE,
                    self.settings.LLM_QUEUE_POLLING_MAX_DELAY_SECONDS,
                )
                continue

        # Max attempts reached
        logger.error(
            f"Max polling attempts ({self.settings.LLM_QUEUE_POLLING_MAX_ATTEMPTS}) reached"
        )
        return None, "Maximum polling attempts reached"

    async def _check_queue_status(self, queue_id: str) -> dict[str, Any] | None:
        """Check the status of a queued request.

        Args:
            queue_id: Queue identifier to check

        Returns:
            Status data dictionary or None on error
        """
        try:
            status_url = f"{self.base_url}/status/{queue_id}"

            async with self.session.get(
                status_url,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response_text = await response.text()

                if response.status == 200:
                    try:
                        status_data: dict[str, Any] = json.loads(response_text)
                        return status_data
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse queue status JSON: {e}")
                        return None

                elif response.status == 404:
                    logger.error(f"Queue ID not found: {queue_id}")
                    return None

                else:
                    logger.error(f"Queue status check failed: HTTP {response.status}")
                    return None

        except aiohttp.ClientError as e:
            logger.error(f"Queue status check request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error checking queue status: {e}")
            return None

    async def _retrieve_queue_result(
        self, queue_id: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Retrieve the result of a completed queue request.

        Args:
            queue_id: Queue identifier to retrieve results for

        Returns:
            Tuple of (response_data, error_message)
        """
        try:
            result_url = f"{self.base_url}/results/{queue_id}"

            async with self.session.get(
                result_url,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response_text = await response.text()

                if response.status == 200:
                    try:
                        response_data = json.loads(response_text)

                        # Extract the comparison result and preserve 1-5 confidence scale
                        # LLM Provider Service returns 1-5 scale, keep as-is for CJ Assessment
                        confidence = response_data.get("confidence", 3.0)

                        result = {
                            "winner": response_data.get("winner"),
                            "justification": response_data.get("justification"),
                            "confidence": confidence,
                        }

                        logger.info(
                            f"Successfully retrieved queued comparison result, "
                            f"queue_id: {queue_id}, "
                            f"provider: {response_data.get('provider')}, "
                            f"model: {response_data.get('model')}, "
                            f"response_time: {response_data.get('response_time_ms', 'N/A')}ms"
                        )

                        return result, None

                    except json.JSONDecodeError as e:
                        error_msg = f"Failed to parse queue result JSON: {str(e)}"
                        logger.error(f"{error_msg}, response: {response_text[:200]}")
                        return None, error_msg

                elif response.status == 202:
                    # Result not ready yet (shouldn't happen if status was "completed")
                    logger.warning(f"Queue result not ready yet for queue_id: {queue_id}")
                    return None, "Queue result not ready yet"

                elif response.status == 404:
                    logger.error(f"Queue result not found: {queue_id}")
                    return None, "Queue result not found"

                elif response.status == 410:
                    logger.error(f"Queue result expired: {queue_id}")
                    return None, "Queue result expired"

                else:
                    logger.error(f"Queue result retrieval failed: HTTP {response.status}")
                    return None, f"Queue result retrieval failed: HTTP {response.status}"

        except aiohttp.ClientError as e:
            error_msg = f"Queue result retrieval request failed: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error retrieving queue result: {str(e)}"
            logger.exception(error_msg)
            return None, error_msg
