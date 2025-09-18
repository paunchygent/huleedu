"""Language Tool Service client implementation."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any
from uuid import UUID

import aiohttp
from common_core.events.nlp_events import GrammarAnalysis, GrammarError
from huleedu_service_libs.error_handling.factories import raise_external_service_error
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerError

from services.nlp_service.protocols import LanguageToolClientProtocol

if TYPE_CHECKING:
    from services.nlp_service.config import Settings

logger = create_service_logger("nlp_service.implementations.language_tool_client")


class LanguageToolServiceClient(LanguageToolClientProtocol):
    """Client for Language Tool Service integration with retry and circuit breaker support."""

    def __init__(self, settings: Settings) -> None:
        """Initialize client with settings.

        Args:
            settings: Service settings containing LanguageTool configuration
        """
        self.service_url = settings.LANGUAGE_TOOL_SERVICE_URL.rstrip("/")
        self.request_timeout = settings.LANGUAGE_TOOL_REQUEST_TIMEOUT
        self.max_retries = settings.LANGUAGE_TOOL_MAX_RETRIES
        self.retry_delay = settings.LANGUAGE_TOOL_RETRY_DELAY
        # Circuit breaker is optionally attached by DI provider
        self._circuit_breaker: CircuitBreaker | None = None

        logger.info(
            f"LanguageToolServiceClient initialized with URL: {self.service_url}",
            extra={
                "timeout": self.request_timeout,
                "max_retries": self.max_retries,
                "retry_delay": self.retry_delay,
            },
        )

    def _map_language_code(self, language: str) -> str:
        """Map language codes to LanguageTool expected format.

        Args:
            language: Input language code ("en", "sv", "auto")

        Returns:
            Mapped language code for LanguageTool API
        """
        mapping = {"en": "en-US", "sv": "sv-SE", "auto": "auto"}
        return mapping.get(language, language)

    def _is_retryable_error(self, status_code: int) -> bool:
        """Determine if HTTP error should be retried.

        Args:
            status_code: HTTP response status code

        Returns:
            True if error should be retried (5xx), False otherwise (4xx)
        """
        return status_code >= 500

    async def _make_request_with_retry(
        self,
        http_session: aiohttp.ClientSession,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        correlation_id: UUID,
    ) -> dict[str, Any]:
        """Make HTTP request with retry logic and exponential backoff.

        Args:
            http_session: HTTP client session
            url: Request URL
            payload: JSON payload
            headers: Request headers
            correlation_id: Request correlation ID

        Returns:
            Response JSON data

        Raises:
            HuleEduError: On all failures after retries exhausted
        """
        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):  # +1 for initial attempt
            try:
                timeout = aiohttp.ClientTimeout(total=self.request_timeout)

                logger.debug(
                    f"Making HTTP POST request (attempt {attempt + 1}/{self.max_retries + 1})",
                    extra={
                        "correlation_id": str(correlation_id),
                        "url": url,
                        "attempt": attempt + 1,
                        "max_attempts": self.max_retries + 1,
                    },
                )

                async with http_session.post(
                    url, json=payload, headers=headers, timeout=timeout
                ) as response:
                    if response.status == 200:
                        result: dict[str, Any] = await response.json()
                        return result

                    # Handle non-200 responses
                    response_text = await response.text()

                    # Check if this is a retryable error
                    if not self._is_retryable_error(response.status):
                        # 4xx errors - don't retry
                        raise_external_service_error(
                            service="nlp_service",
                            operation="check_grammar",
                            external_service="language_tool_service",
                            message=f"Language Tool Service returned {response.status}: {response_text}",  # noqa: E501
                            correlation_id=correlation_id,
                            status_code=response.status,
                            response_text=response_text[:500],
                        )

                    # 5xx errors - will retry if attempts remaining
                    if attempt == self.max_retries:
                        # Final attempt failed
                        raise_external_service_error(
                            service="nlp_service",
                            operation="check_grammar",
                            external_service="language_tool_service",
                            message=f"Language Tool Service returned {response.status} after {self.max_retries + 1} attempts: {response_text}",  # noqa: E501
                            correlation_id=correlation_id,
                            status_code=response.status,
                            response_text=response_text[:500],
                            attempts_made=self.max_retries + 1,
                        )

                    logger.warning(
                        f"HTTP {response.status} error, will retry (attempt {attempt + 1}/{self.max_retries + 1})",  # noqa: E501
                        extra={
                            "correlation_id": str(correlation_id),
                            "status_code": response.status,
                            "attempt": attempt + 1,
                        },
                    )

            except aiohttp.ClientError as e:
                last_exception = e

                if attempt == self.max_retries:
                    # Final attempt failed with client error
                    raise_external_service_error(
                        service="nlp_service",
                        operation="check_grammar",
                        external_service="language_tool_service",
                        message=f"Failed to connect to Language Tool Service after {self.max_retries + 1} attempts: {str(e)}",  # noqa: E501
                        correlation_id=correlation_id,
                        error_type=type(e).__name__,
                        attempts_made=self.max_retries + 1,
                    )

                logger.warning(
                    f"HTTP client error, will retry (attempt {attempt + 1}/{self.max_retries + 1}): {e}",  # noqa: E501
                    extra={
                        "correlation_id": str(correlation_id),
                        "error_type": type(e).__name__,
                        "attempt": attempt + 1,
                    },
                )

            # Calculate exponential backoff delay
            if attempt < self.max_retries:
                delay = self.retry_delay * (2**attempt)
                logger.debug(
                    f"Waiting {delay:.2f}s before retry",
                    extra={"correlation_id": str(correlation_id), "delay_seconds": delay},
                )
                await asyncio.sleep(delay)

        # Should never reach here, but safety fallback
        raise_external_service_error(
            service="nlp_service",
            operation="check_grammar",
            external_service="language_tool_service",
            message=f"Unexpected failure after retry loop: {last_exception}",
            correlation_id=correlation_id,
            error_type=type(last_exception).__name__ if last_exception else "Unknown",
        )

    def _parse_response_to_grammar_errors(  # noqa: E501
        self, response_data: dict[str, Any]
    ) -> list[GrammarError]:
        """Parse LanguageTool response into GrammarError objects.

        Args:
            response_data: JSON response from LanguageTool service

        Returns:
            List of GrammarError objects
        """
        errors = []

        for match in response_data.get("matches", []):
            rule = match.get("rule", {})
            category = rule.get("category", {})
            context = match.get("context", {})

            # Extract replacements
            replacements = []
            for replacement in match.get("replacements", []):
                if isinstance(replacement, dict):
                    replacements.append(replacement.get("value", ""))
                else:
                    replacements.append(str(replacement))

            grammar_error = GrammarError(
                rule_id=rule.get("id", "UNKNOWN_RULE"),
                message=match.get("message", ""),
                short_message=match.get("shortMessage", ""),
                offset=match.get("offset", 0),
                length=match.get("length", 0),
                replacements=replacements,
                category=category.get("id", "unknown").lower(),
                severity=match.get("type", {}).get("typeName", "info").lower()
                if isinstance(match.get("type"), dict)
                else "info",
                category_id=category.get("id", "UNKNOWN"),
                category_name=category.get("name", "Unknown"),
                context=context.get("text", ""),
                context_offset=context.get("offset", 0),
            )

            errors.append(grammar_error)

        return errors

    async def check_grammar(
        self,
        text: str,
        http_session: aiohttp.ClientSession,
        correlation_id: UUID,
        language: str = "auto",
    ) -> GrammarAnalysis:
        """Check grammar using Language Tool Service with retry and circuit breaker support.

        Args:
            text: The text to check for grammar errors
            http_session: HTTP session for external API calls
            correlation_id: Correlation ID for tracking
            language: Language code ("en", "sv") or "auto"

        Returns:
            GrammarAnalysis with errors from LanguageTool service
        """
        start_time = time.time()

        logger.debug(
            "Checking grammar for text",
            extra={
                "correlation_id": str(correlation_id),
                "text_length": len(text),
                "language": language,
            },
        )

        # Check if circuit breaker is available and open
        if self._circuit_breaker is not None:
            try:
                # Use circuit breaker if available
                response_data = await self._circuit_breaker.call(
                    self._make_request_with_retry,
                    http_session,
                    f"{self.service_url}/v1/check",
                    {
                        "text": text,
                        "language": self._map_language_code(language),
                    },
                    {
                        "X-Correlation-ID": str(correlation_id),
                        "Content-Type": "application/json",
                    },
                    correlation_id,
                )
            except CircuitBreakerError as e:
                # Circuit is open - return graceful degradation
                processing_time_ms = int((time.time() - start_time) * 1000)

                logger.warning(
                    "Circuit breaker is open, returning empty grammar analysis",
                    extra={
                        "correlation_id": str(correlation_id),
                        "circuit_breaker_error": str(e),
                        "processing_time_ms": processing_time_ms,
                    },
                )

                return GrammarAnalysis(
                    error_count=0,
                    errors=[],
                    language=self._map_language_code(language) if language != "auto" else "en",
                    processing_time_ms=processing_time_ms,
                )
        else:
            # No circuit breaker - direct call
            response_data = await self._make_request_with_retry(
                http_session,
                f"{self.service_url}/v1/check",
                {
                    "text": text,
                    "language": self._map_language_code(language),
                },
                {
                    "X-Correlation-ID": str(correlation_id),
                    "Content-Type": "application/json",
                },
                correlation_id,
            )

        # Log the actual response for visibility
        logger.debug(
            "Language Tool Service raw response received",
            extra={
                "correlation_id": str(correlation_id),
                "response_type": type(response_data).__name__,
                "response_keys": list(response_data.keys()) if isinstance(response_data, dict) else None,
                "language_field": response_data.get("language") if isinstance(response_data, dict) else None,
                "language_field_type": type(response_data.get("language")).__name__ if isinstance(response_data, dict) else None,
                "total_errors": response_data.get("total_grammar_errors") if isinstance(response_data, dict) else None,
                "has_matches": bool(response_data.get("matches")) if isinstance(response_data, dict) else None,
            },
        )

        # Parse response into GrammarError objects
        errors = self._parse_response_to_grammar_errors(response_data)

        # Calculate processing time
        processing_time_ms = int((time.time() - start_time) * 1000)

        # Determine detected language from response or use input
        # Language Tool Service returns flat structure: {"language": "en-US"}
        detected_language = response_data.get("language", language)
        if detected_language == "auto":
            detected_language = "en"  # Default fallback

        logger.info(
            f"Grammar check completed: {len(errors)} errors found",
            extra={
                "correlation_id": str(correlation_id),
                "error_count": len(errors),
                "language": detected_language,
                "processing_time_ms": processing_time_ms,
            },
        )

        return GrammarAnalysis(
            error_count=len(errors),
            errors=errors,
            language=detected_language,
            processing_time_ms=processing_time_ms,
            grammar_category_counts=response_data.get("grammar_category_counts"),
            grammar_rule_counts=response_data.get("grammar_rule_counts"),
        )
