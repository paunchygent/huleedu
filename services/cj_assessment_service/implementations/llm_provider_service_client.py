"""HTTP client for LLM Provider Service.

This implementation replaces direct LLM provider calls with HTTP requests
to the centralized LLM Provider Service.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import aiohttp
from huleedu_service_libs.logging_utils import create_service_logger

from common_core.error_enums import ErrorCode
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.exceptions import (
    map_status_to_error_code,
)
from services.cj_assessment_service.models_api import ErrorDetail
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
        correlation_id: UUID,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
        provider_override: str | None = None,
    ) -> tuple[dict[str, Any] | None, ErrorDetail | None]:
        """Generate comparison via LLM Provider Service.

        Handles both immediate (200) and queued (202) responses from the LLM Provider Service.
        For queued responses, implements polling with exponential backoff.

        Args:
            user_prompt: The user prompt containing essay comparison request
            correlation_id: Correlation ID for request tracing
            system_prompt_override: Optional system prompt override
            model_override: Optional model name override
            temperature_override: Optional temperature override (0.0-2.0)
            max_tokens_override: Optional max tokens override
            provider_override: Optional provider name override

        Returns:
            Tuple of (response_data, error_detail)
        """
        # Extract essays from the formatted prompt
        extraction_result = self._extract_essays_from_prompt(user_prompt)
        if not extraction_result:
            error_detail = ErrorDetail(
                error_code=ErrorCode.VALIDATION_ERROR,
                message="Invalid prompt format: Could not extract essays",
                correlation_id=correlation_id,
                timestamp=datetime.now(UTC),
                details={"prompt_length": len(user_prompt)},
            )
            logger.error(
                "Could not extract essays from prompt",
                extra={
                    "error_code": error_detail.error_code.value,
                    "correlation_id": str(correlation_id),
                    "prompt_length": len(user_prompt),
                },
            )
            return None, error_detail

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
            "correlation_id": str(correlation_id),
        }

        # Make initial HTTP request with retry logic
        url = f"{self.base_url}/comparison"

        async def make_request() -> tuple[dict[str, Any] | None, ErrorDetail | None]:
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
                        return await self._handle_immediate_response(response_text, correlation_id)

                    elif response.status == 202:
                        # Queued response - start polling
                        return await self._handle_queued_response(response_text, correlation_id)

                    else:
                        # Check if error is retryable
                        try:
                            error_data = json.loads(response_text)
                            is_retryable = response.status in [
                                429,
                                500,
                                502,
                                503,
                                504,
                            ] or error_data.get("is_retryable", False)

                            if is_retryable:
                                # Log before raising for better debugging
                                logger.warning(
                                    "Retryable error from LLM Provider Service",
                                    extra={
                                        "status_code": response.status,
                                        "error": error_data.get("error", "Unknown"),
                                        "correlation_id": str(correlation_id),
                                        "provider": provider_override
                                        or self.settings.DEFAULT_LLM_PROVIDER.value,
                                    },
                                )
                                # Create proper exception with details
                                raise aiohttp.ClientResponseError(
                                    request_info=response.request_info,
                                    history=response.history,
                                    status=response.status,
                                    message=error_data.get("error", str(response.status)),
                                    headers=response.headers,
                                )
                        except json.JSONDecodeError:
                            # If we can't parse JSON, use status code to decide
                            if response.status in [429, 500, 502, 503, 504]:
                                logger.warning(
                                    "Retryable HTTP error (no JSON body)",
                                    extra={
                                        "status_code": response.status,
                                        "correlation_id": str(correlation_id),
                                    },
                                )
                                response.raise_for_status()

                        # Non-retryable error - return error tuple
                        return await self._handle_error_response(
                            response.status, response_text, correlation_id
                        )

            except aiohttp.ClientError:
                # Re-raise to let retry manager handle it
                raise
            except Exception as e:
                error_detail = ErrorDetail(
                    error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
                    message=f"Unexpected error calling LLM Provider Service: {str(e)}",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    details={"exception_type": type(e).__name__},
                )
                logger.exception(
                    "Unexpected error calling LLM Provider Service",
                    extra={
                        "error_code": error_detail.error_code.value,
                        "correlation_id": str(correlation_id),
                        "exception_type": type(e).__name__,
                    },
                )
                return None, error_detail

        # Use retry manager for resilience
        result, error = await self.retry_manager.with_retry(make_request)

        return result, error

    async def _handle_immediate_response(
        self, response_text: str, correlation_id: UUID
    ) -> tuple[dict[str, Any] | None, ErrorDetail | None]:
        """Handle immediate (200) response from LLM Provider Service.

        Args:
            response_text: Raw response text from the HTTP response
            correlation_id: Correlation ID for request tracing

        Returns:
            Tuple of (response_data, error_detail)
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
            error_detail = ErrorDetail(
                error_code=ErrorCode.PARSING_ERROR,
                message=f"Failed to parse immediate response JSON: {str(e)}",
                correlation_id=correlation_id,
                timestamp=datetime.now(UTC),
                details={"response_preview": response_text[:200]},
            )
            logger.error(
                "Failed to parse immediate response JSON",
                extra={
                    "error_code": error_detail.error_code.value,
                    "correlation_id": str(correlation_id),
                    "response_preview": response_text[:200],
                },
            )
            return None, error_detail

    async def _handle_queued_response(
        self, response_text: str, correlation_id: UUID
    ) -> tuple[dict[str, Any] | None, ErrorDetail | None]:
        """Handle queued (202) response from LLM Provider Service.

        Args:
            response_text: Raw response text from the HTTP response
            correlation_id: Correlation ID for request tracing

        Returns:
            Tuple of (response_data, error_detail)
        """
        try:
            queue_response = json.loads(response_text)
            queue_id = queue_response.get("queue_id")

            if not queue_id:
                error_detail = ErrorDetail(
                    error_code=ErrorCode.INVALID_RESPONSE,
                    message="Queue response missing queue_id",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    details={"response_preview": response_text[:200]},
                )
                logger.error(
                    "Queue response missing queue_id",
                    extra={
                        "error_code": error_detail.error_code.value,
                        "correlation_id": str(correlation_id),
                        "response_preview": response_text[:200],
                    },
                )
                return None, error_detail

            logger.info(
                "Request queued for processing",
                extra={
                    "correlation_id": str(correlation_id),
                    "queue_id": queue_id,
                    "estimated_wait_minutes": queue_response.get("estimated_wait_minutes", "N/A"),
                },
            )

            # Check if polling is disabled
            if not self.settings.LLM_QUEUE_POLLING_ENABLED:
                error_detail = ErrorDetail(
                    error_code=ErrorCode.CONFIGURATION_ERROR,
                    message="Request queued but polling is disabled",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    details={"queue_id": queue_id},
                )
                logger.error(
                    "Request queued but polling is disabled",
                    extra={
                        "error_code": error_detail.error_code.value,
                        "correlation_id": str(correlation_id),
                        "queue_id": queue_id,
                    },
                )
                return None, error_detail

            # Start polling for results
            return await self._poll_for_results(queue_id, correlation_id)

        except json.JSONDecodeError as e:
            error_detail = ErrorDetail(
                error_code=ErrorCode.PARSING_ERROR,
                message=f"Failed to parse queued response JSON: {str(e)}",
                correlation_id=correlation_id,
                timestamp=datetime.now(UTC),
                details={"response_preview": response_text[:200]},
            )
            logger.error(
                "Failed to parse queued response JSON",
                extra={
                    "error_code": error_detail.error_code.value,
                    "correlation_id": str(correlation_id),
                    "response_preview": response_text[:200],
                },
            )
            return None, error_detail

    async def _handle_error_response(
        self, status_code: int, response_text: str, correlation_id: UUID
    ) -> tuple[dict[str, Any] | None, ErrorDetail | None]:
        """Handle error responses from LLM Provider Service.

        Args:
            status_code: HTTP status code
            response_text: Raw response text from the HTTP response
            correlation_id: Correlation ID for request tracing

        Returns:
            Tuple of (response_data, error_detail)
        """
        try:
            error_data = json.loads(response_text)
            error_msg = error_data.get("error", f"HTTP {status_code}")
            details_text = error_data.get("details", "")
            is_retryable = error_data.get("is_retryable", status_code in [429, 500, 502, 503, 504])

            details = {
                "status_code": status_code,
                "is_retryable": is_retryable,
                "details_text": details_text,
                "response_preview": response_text[:200],
            }
        except json.JSONDecodeError:
            error_msg = f"HTTP {status_code}"
            details = {
                "status_code": status_code,
                "is_retryable": status_code in [429, 500, 502, 503, 504],
                "response_preview": response_text[:200],
            }

        error_code = map_status_to_error_code(status_code)
        error_detail = ErrorDetail(
            error_code=error_code,
            message=f"LLM Provider Service error: {error_msg}",
            correlation_id=correlation_id,
            timestamp=datetime.now(UTC),
            details=details,
        )

        logger.error(
            "LLM Provider Service error",
            extra={
                "error_code": error_detail.error_code.value,
                "correlation_id": str(correlation_id),
                "status_code": status_code,
                "is_retryable": details.get("is_retryable", False),
            },
        )
        return None, error_detail

    async def _poll_for_results(
        self, queue_id: str, correlation_id: UUID
    ) -> tuple[dict[str, Any] | None, ErrorDetail | None]:
        """Poll for results from the queue using exponential backoff.

        Args:
            queue_id: Queue identifier to poll for results
            correlation_id: Correlation ID for request tracing

        Returns:
            Tuple of (response_data, error_detail)
        """
        start_time = time.time()
        attempt = 0
        delay = self.settings.LLM_QUEUE_POLLING_INITIAL_DELAY_SECONDS

        logger.info(
            "Starting queue polling",
            extra={"correlation_id": str(correlation_id), "queue_id": queue_id},
        )

        while attempt < self.settings.LLM_QUEUE_POLLING_MAX_ATTEMPTS:
            # Check total timeout
            timeout_seconds = self.settings.LLM_QUEUE_TOTAL_TIMEOUT_SECONDS
            if time.time() - start_time > timeout_seconds:
                error_detail = ErrorDetail(
                    error_code=ErrorCode.TIMEOUT,
                    message=f"Queue polling timed out after {timeout_seconds} seconds",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    details={"queue_id": queue_id, "timeout_seconds": timeout_seconds},
                )
                logger.error(
                    "Queue polling timed out",
                    extra={
                        "error_code": error_detail.error_code.value,
                        "correlation_id": str(correlation_id),
                        "queue_id": queue_id,
                        "timeout_seconds": timeout_seconds,
                    },
                )
                return None, error_detail

            # Wait before polling (except first attempt)
            if attempt > 0:
                logger.debug(f"Waiting {delay:.1f}s before next poll attempt {attempt + 1}")
                await asyncio.sleep(delay)

            # Check queue status
            status_result = await self._check_queue_status(queue_id, correlation_id)
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
                return await self._retrieve_queue_result(queue_id, correlation_id)

            elif status == "failed":
                error_msg = status_result.get("error_message", "Queue processing failed")
                error_detail = ErrorDetail(
                    error_code=ErrorCode.PROCESSING_ERROR,
                    message=f"Queue processing failed: {error_msg}",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    details={"queue_id": queue_id, "original_error": error_msg},
                )
                logger.error(
                    "Queue processing failed",
                    extra={
                        "error_code": error_detail.error_code.value,
                        "correlation_id": str(correlation_id),
                        "queue_id": queue_id,
                        "original_error": error_msg,
                    },
                )
                return None, error_detail

            elif status == "expired":
                error_detail = ErrorDetail(
                    error_code=ErrorCode.TIMEOUT,
                    message="Queue request expired",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    details={"queue_id": queue_id},
                )
                logger.error(
                    "Queue request expired",
                    extra={
                        "error_code": error_detail.error_code.value,
                        "correlation_id": str(correlation_id),
                        "queue_id": queue_id,
                    },
                )
                return None, error_detail

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
        error_detail = ErrorDetail(
            error_code=ErrorCode.TIMEOUT,
            message=(
                f"Maximum polling attempts ({self.settings.LLM_QUEUE_POLLING_MAX_ATTEMPTS}) reached"
            ),
            correlation_id=correlation_id,
            timestamp=datetime.now(UTC),
            details={
                "queue_id": queue_id,
                "max_attempts": self.settings.LLM_QUEUE_POLLING_MAX_ATTEMPTS,
            },
        )
        logger.error(
            "Maximum polling attempts reached",
            extra={
                "error_code": error_detail.error_code.value,
                "correlation_id": str(correlation_id),
                "queue_id": queue_id,
                "max_attempts": self.settings.LLM_QUEUE_POLLING_MAX_ATTEMPTS,
            },
        )
        return None, error_detail

    async def _check_queue_status(
        self, queue_id: str, correlation_id: UUID
    ) -> dict[str, Any] | None:
        """Check the status of a queued request with retry logic.

        Args:
            queue_id: Queue identifier to check
            correlation_id: Correlation ID for request tracing

        Returns:
            Status data dictionary or None on error
        """

        async def make_status_request() -> tuple[dict[str, Any] | None, ErrorDetail | None]:
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
                            return status_data, None
                        except json.JSONDecodeError as e:
                            error_detail = ErrorDetail(
                                error_code=ErrorCode.PARSING_ERROR,
                                message=f"Failed to parse queue status JSON: {e}",
                                correlation_id=correlation_id,
                                timestamp=datetime.now(UTC),
                                details={
                                    "queue_id": queue_id,
                                    "response_preview": response_text[:200],
                                },
                            )
                            logger.error(
                                "Failed to parse queue status JSON",
                                extra={
                                    "error_code": error_detail.error_code.value,
                                    "correlation_id": str(correlation_id),
                                    "queue_id": queue_id,
                                },
                            )
                            return None, error_detail

                    elif response.status == 404:
                        error_detail = ErrorDetail(
                            error_code=ErrorCode.RESOURCE_NOT_FOUND,
                            message=f"Queue ID not found: {queue_id}",
                            correlation_id=correlation_id,
                            timestamp=datetime.now(UTC),
                            details={"queue_id": queue_id},
                        )
                        logger.error(
                            "Queue ID not found",
                            extra={
                                "error_code": error_detail.error_code.value,
                                "correlation_id": str(correlation_id),
                                "queue_id": queue_id,
                            },
                        )
                        return None, error_detail

                    else:
                        # Check if error is retryable
                        if response.status in [429, 500, 502, 503, 504]:
                            # Raise for retry
                            response.raise_for_status()

                        error_detail = ErrorDetail(
                            error_code=map_status_to_error_code(response.status),
                            message=f"Queue status check failed: HTTP {response.status}",
                            correlation_id=correlation_id,
                            timestamp=datetime.now(UTC),
                            details={"queue_id": queue_id, "status_code": response.status},
                        )
                        logger.error(
                            "Queue status check failed",
                            extra={
                                "error_code": error_detail.error_code.value,
                                "correlation_id": str(correlation_id),
                                "queue_id": queue_id,
                                "status_code": response.status,
                            },
                        )
                        return None, error_detail

            except aiohttp.ClientError:
                # Re-raise to let retry manager handle it
                raise
            except Exception as e:
                error_detail = ErrorDetail(
                    error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
                    message=f"Unexpected error checking queue status: {e}",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    details={"queue_id": queue_id, "exception_type": type(e).__name__},
                )
                logger.error(
                    "Unexpected error checking queue status",
                    extra={
                        "error_code": error_detail.error_code.value,
                        "correlation_id": str(correlation_id),
                        "queue_id": queue_id,
                        "exception_type": type(e).__name__,
                    },
                )
                return None, error_detail

        # Use retry manager for resilience
        result, error = await self.retry_manager.with_retry(make_status_request)
        if error:
            logger.debug(f"Queue status check failed after retries: {error.message}")
            return None
        # Result is dict[str, Any] | None from make_status_request
        return result if isinstance(result, dict) else None

    async def _retrieve_queue_result(
        self, queue_id: str, correlation_id: UUID
    ) -> tuple[dict[str, Any] | None, ErrorDetail | None]:
        """Retrieve the result of a completed queue request with retry logic.

        Args:
            queue_id: Queue identifier to retrieve results for
            correlation_id: Correlation ID for request tracing

        Returns:
            Tuple of (response_data, error_detail)
        """

        async def make_result_request() -> tuple[dict[str, Any] | None, ErrorDetail | None]:
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
                                "Successfully retrieved queued comparison result",
                                extra={
                                    "correlation_id": str(correlation_id),
                                    "queue_id": queue_id,
                                    "provider": response_data.get("provider"),
                                    "model": response_data.get("model"),
                                    "response_time_ms": response_data.get(
                                        "response_time_ms", "N/A"
                                    ),
                                },
                            )

                            return result, None

                        except json.JSONDecodeError as e:
                            error_detail = ErrorDetail(
                                error_code=ErrorCode.PARSING_ERROR,
                                message=f"Failed to parse queue result JSON: {str(e)}",
                                correlation_id=correlation_id,
                                timestamp=datetime.now(UTC),
                                details={
                                    "queue_id": queue_id,
                                    "response_preview": response_text[:200],
                                },
                            )
                            logger.error(
                                "Failed to parse queue result JSON",
                                extra={
                                    "error_code": error_detail.error_code.value,
                                    "correlation_id": str(correlation_id),
                                    "queue_id": queue_id,
                                    "response_preview": response_text[:200],
                                },
                            )
                            return None, error_detail

                    elif response.status == 202:
                        # Result not ready yet (shouldn't happen if status was "completed")
                        error_detail = ErrorDetail(
                            error_code=ErrorCode.PROCESSING_ERROR,
                            message="Queue result not ready yet",
                            correlation_id=correlation_id,
                            timestamp=datetime.now(UTC),
                            details={"queue_id": queue_id},
                        )
                        logger.warning(
                            "Queue result not ready yet",
                            extra={"correlation_id": str(correlation_id), "queue_id": queue_id},
                        )
                        return None, error_detail

                    elif response.status == 404:
                        error_detail = ErrorDetail(
                            error_code=ErrorCode.RESOURCE_NOT_FOUND,
                            message="Queue result not found",
                            correlation_id=correlation_id,
                            timestamp=datetime.now(UTC),
                            details={"queue_id": queue_id},
                        )
                        logger.error(
                            "Queue result not found",
                            extra={
                                "error_code": error_detail.error_code.value,
                                "correlation_id": str(correlation_id),
                                "queue_id": queue_id,
                            },
                        )
                        return None, error_detail

                    elif response.status == 410:
                        error_detail = ErrorDetail(
                            error_code=ErrorCode.TIMEOUT,
                            message="Queue result expired",
                            correlation_id=correlation_id,
                            timestamp=datetime.now(UTC),
                            details={"queue_id": queue_id},
                        )
                        logger.error(
                            "Queue result expired",
                            extra={
                                "error_code": error_detail.error_code.value,
                                "correlation_id": str(correlation_id),
                                "queue_id": queue_id,
                            },
                        )
                        return None, error_detail

                    else:
                        # Check if error is retryable
                        if response.status in [429, 500, 502, 503, 504]:
                            # Raise for retry
                            response.raise_for_status()

                        error_detail = ErrorDetail(
                            error_code=map_status_to_error_code(response.status),
                            message=f"Queue result retrieval failed: HTTP {response.status}",
                            correlation_id=correlation_id,
                            timestamp=datetime.now(UTC),
                            details={"queue_id": queue_id, "status_code": response.status},
                        )
                        logger.error(
                            "Queue result retrieval failed",
                            extra={
                                "error_code": error_detail.error_code.value,
                                "correlation_id": str(correlation_id),
                                "queue_id": queue_id,
                                "status_code": response.status,
                            },
                        )
                        return None, error_detail

            except aiohttp.ClientError:
                # Re-raise to let retry manager handle it
                raise
            except Exception as e:
                error_detail = ErrorDetail(
                    error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
                    message=f"Unexpected error retrieving queue result: {str(e)}",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    details={"queue_id": queue_id, "exception_type": type(e).__name__},
                )
                logger.exception(
                    "Unexpected error retrieving queue result",
                    extra={
                        "error_code": error_detail.error_code.value,
                        "correlation_id": str(correlation_id),
                        "queue_id": queue_id,
                        "exception_type": type(e).__name__,
                    },
                )
                return None, error_detail

        # Use retry manager for resilience
        result, error = await self.retry_manager.with_retry(make_result_request)
        if error:
            logger.debug(f"Queue result retrieval failed after retries: {error.message}")
            return None, error
        return result, None
