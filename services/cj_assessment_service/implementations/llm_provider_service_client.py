"""HTTP client for LLM Provider Service.

This implementation replaces direct LLM provider calls with HTTP requests
to the centralized LLM Provider Service.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import aiohttp
from common_core import LLMProviderType
from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_authentication_error,
    raise_external_service_error,
    raise_invalid_request,
    raise_invalid_response,
    raise_parsing_error,
    raise_rate_limit_error,
    raise_resource_not_found,
    raise_service_unavailable,
    raise_timeout_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.protocols import LLMProviderProtocol, RetryManagerProtocol
from services.llm_provider_service.api_models import (
    LLMConfigOverrides as ProviderLLMConfigOverrides,
)

logger = create_service_logger("cj_assessment_service.llm_provider_service_client")


def _build_llm_config_override_payload(
    *,
    provider_override: str | LLMProviderType | None = None,
    model_override: str | None = None,
    temperature_override: float | None = None,
    system_prompt_override: str | None = None,
    max_tokens_override: int | None = None,
) -> dict[str, Any] | None:
    """Convert CJ overrides into the provider service payload."""
    provider_enum: LLMProviderType | None = None
    if isinstance(provider_override, LLMProviderType):
        provider_enum = provider_override
    elif isinstance(provider_override, str):
        normalized = provider_override.strip().lower()
        try:
            provider_enum = LLMProviderType(normalized)
        except ValueError:
            logger.warning(
                "Unknown provider_override supplied; default provider will be used",
                extra={"provider_override": provider_override},
            )

    overrides_model = ProviderLLMConfigOverrides(
        provider_override=provider_enum,
        model_override=model_override,
        temperature_override=temperature_override,
        system_prompt_override=system_prompt_override,
        max_tokens_override=max_tokens_override,
    )
    payload = overrides_model.model_dump(exclude_none=True)
    return payload or None


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

    async def generate_comparison(
        self,
        user_prompt: str,
        correlation_id: UUID,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
        provider_override: str | None = None,
        request_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Generate comparison via LLM Provider Service.

        Handles both immediate (200) and queued (202) responses from the LLM Provider Service.
        For queued responses, returns None and expects results via callback.

        Args:
            user_prompt: The user prompt containing essay comparison request
            correlation_id: Correlation ID for request tracing
            system_prompt_override: Optional system prompt override
            model_override: Optional model name override
            temperature_override: Optional temperature override (0.0-2.0)
            max_tokens_override: Optional max tokens override
            provider_override: Optional provider name override

        Returns:
            Comparison result dict for immediate responses, None for queued responses
        """
        # Build request body for LLM Provider Service
        # Note: user_prompt now contains the complete prompt with essays embedded
        overrides_payload = _build_llm_config_override_payload(
            provider_override=provider_override or self.settings.DEFAULT_LLM_PROVIDER.value,
            model_override=model_override or self.settings.DEFAULT_LLM_MODEL,
            temperature_override=temperature_override or self.settings.DEFAULT_LLM_TEMPERATURE,
            system_prompt_override=system_prompt_override,
            max_tokens_override=max_tokens_override,
        )

        request_body = {
            "user_prompt": user_prompt,
            "metadata": request_metadata or {},
            "correlation_id": str(correlation_id),
            "callback_topic": self.settings.LLM_PROVIDER_CALLBACK_TOPIC,  # Required field
        }
        if overrides_payload:
            request_body["llm_config_overrides"] = overrides_payload

        logger.info(
            f"Sending LLM comparison request with correlation_id: {correlation_id}",
            extra={"prompt_length": len(user_prompt)},
        )

        # Make initial HTTP request with retry logic
        url = f"{self.base_url}/comparison"

        async def make_request() -> dict[str, Any] | None:
            try:
                async with self.session.post(
                    url,
                    json=request_body,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=60),  # 60 second timeout
                ) as response:
                    response_text = await response.text()

                    if response.status == 202:
                        # ALL LLM requests are async - this is the ONLY valid success response
                        # LLM processing takes 10-30+ seconds, blocking HTTP is an anti-pattern
                        await self._handle_queued_response(response_text, correlation_id)
                        return None  # Always return None - results come via Kafka callbacks

                    elif response.status == 200:
                        # This should never happen in production - LLM Provider should always queue
                        logger.error(
                            "LLM Provider returned 200 (sync) - "
                            "this is an architectural violation. "
                            "All LLM calls must be async (202) with Kafka callbacks.",
                            extra={
                                "correlation_id": str(correlation_id),
                                "provider": provider_override
                                or self.settings.DEFAULT_LLM_PROVIDER.value,
                            },
                        )
                        # Treat as an error - we don't support synchronous LLM calls
                        raise_invalid_response(
                            service="cj_assessment_service",
                            operation="generate_comparison",
                            message="LLM Provider returned synchronous response (200). "
                            "Only async (202) responses are supported.",
                            correlation_id=correlation_id,
                            response_status=200,
                        )

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

                        # Non-retryable error - handle and raise
                        await self._handle_error_response(
                            response.status, response_text, correlation_id
                        )
                        # This should never be reached as _handle_error_response raises
                        raise AssertionError("_handle_error_response should have raised")

            except aiohttp.ClientError:
                # Re-raise to let retry manager handle it
                raise
            except HuleEduError:
                # Re-raise HuleEduError as-is (preserve error code semantics)
                raise
            except Exception as e:
                # Only convert unexpected raw exceptions to structured errors
                raise_external_service_error(
                    service="cj_assessment_service",
                    operation="generate_comparison.make_request",
                    external_service="llm_provider_service",
                    message=f"Unexpected error calling LLM Provider Service: {str(e)}",
                    correlation_id=correlation_id,
                    exception_type=type(e).__name__,
                )

        # Use retry manager directly - circuit breaker should be integrated into the HTTP client
        # or applied at the transport layer for async compatibility
        return await self.retry_manager.with_retry(make_request)

    # REMOVED: _handle_immediate_response method
    # This method was removed as part of the architectural simplification.
    # ALL LLM calls are async (202) with Kafka callbacks.
    # Synchronous responses (200) are an anti-pattern for LLM integration.
    # LLMs take 10-30+ seconds - blocking HTTP for this duration is wasteful.

    async def _handle_queued_response(self, response_text: str, correlation_id: UUID) -> None:
        """Handle queued (202) response from LLM Provider Service.

        No polling is performed - the service will send results via callback.

        Args:
            response_text: Raw response text from the HTTP response
            correlation_id: Correlation ID for request tracing

        Returns:
            None - results will be delivered via callback
        """
        try:
            queue_response = json.loads(response_text)
            queue_id = queue_response.get("queue_id")

            if not queue_id:
                raise_invalid_response(
                    service="cj_assessment_service",
                    operation="_handle_queued_response",
                    expected="queue_id in response",
                    actual="missing queue_id",
                    message="Queue response missing queue_id",
                    correlation_id=correlation_id,
                    response_preview=response_text[:200],
                )

            logger.info(
                "Request queued for processing - results will be delivered via callback",
                extra={
                    "correlation_id": str(correlation_id),
                    "queue_id": queue_id,
                    "estimated_wait_minutes": queue_response.get("estimated_wait_minutes", "N/A"),
                    "callback_topic": self.settings.LLM_PROVIDER_CALLBACK_TOPIC,
                },
            )

            # No polling - return None to indicate async processing
            return None

        except json.JSONDecodeError as e:
            raise_parsing_error(
                service="cj_assessment_service",
                operation="_handle_queued_response",
                parse_target="queued_response_json",
                message=f"Failed to parse queued response JSON: {str(e)}",
                correlation_id=correlation_id,
                response_preview=response_text[:200],
            )

    async def _handle_error_response(
        self, status_code: int, response_text: str, correlation_id: UUID
    ) -> None:
        """Handle error responses from LLM Provider Service.

        Args:
            status_code: HTTP status code
            response_text: Raw response text from the HTTP response
            correlation_id: Correlation ID for request tracing

        Raises:
            HuleEduError: Always raises appropriate error based on status code
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

        # Map status codes directly to appropriate factory functions
        if status_code == 400:
            raise_invalid_request(
                service="cj_assessment_service",
                operation="_handle_error_response",
                message=f"LLM Provider Service error: {error_msg}",
                correlation_id=correlation_id,
                **details,
            )
        elif status_code in [401, 403]:
            raise_authentication_error(
                service="cj_assessment_service",
                operation="_handle_error_response",
                message=f"LLM Provider Service error: {error_msg}",
                correlation_id=correlation_id,
                **details,
            )
        elif status_code == 404:
            raise_resource_not_found(
                service="cj_assessment_service",
                operation="_handle_error_response",
                resource_type="LLM Provider endpoint",
                resource_id="N/A",
                message=f"LLM Provider Service error: {error_msg}",
                correlation_id=correlation_id,
                **details,
            )
        elif status_code in [408, 504]:
            raise_timeout_error(
                service="cj_assessment_service",
                operation="_handle_error_response",
                timeout_seconds=60,
                message=f"LLM Provider Service error: {error_msg}",
                correlation_id=correlation_id,
                **details,
            )
        elif status_code == 429:
            raise_rate_limit_error(
                service="cj_assessment_service",
                operation="_handle_error_response",
                message=f"LLM Provider Service error: {error_msg}",
                correlation_id=correlation_id,
                **details,
            )
        elif status_code in [502, 503]:
            raise_service_unavailable(
                service="cj_assessment_service",
                operation="_handle_error_response",
                unavailable_service="llm_provider_service",
                message=f"LLM Provider Service error: {error_msg}",
                correlation_id=correlation_id,
                **details,
            )
        else:
            # Default to external service error
            raise_external_service_error(
                service="cj_assessment_service",
                operation="_handle_error_response",
                external_service="llm_provider_service",
                message=f"LLM Provider Service error: {error_msg}",
                correlation_id=correlation_id,
                **details,
            )
