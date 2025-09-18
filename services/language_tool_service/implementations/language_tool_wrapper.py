"""
Production implementation of Language Tool wrapper.

This module provides the real Language Tool integration that communicates
with the Java LanguageTool server process for grammar analysis.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import aiohttp
from huleedu_service_libs.error_handling import (
    raise_external_service_error,
    raise_service_unavailable,
    raise_timeout_error,
)
from huleedu_service_libs.error_handling.correlation import CorrelationContext
from huleedu_service_libs.logging_utils import create_service_logger

from services.language_tool_service.config import Settings
from services.language_tool_service.implementations.language_tool_manager import (
    LanguageToolManager,
)
from services.language_tool_service.protocols import LanguageToolWrapperProtocol

logger = create_service_logger("language_tool_service.implementations.language_tool_wrapper")


class LanguageToolWrapper(LanguageToolWrapperProtocol):
    """
    Production implementation of Language Tool wrapper.

    This implementation communicates with the actual LanguageTool Java server
    for grammar analysis, with category filtering and proper error handling.
    """

    def __init__(
        self,
        settings: Settings,
        manager: LanguageToolManager,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the Language Tool wrapper.

        Args:
            settings: Service configuration settings
            manager: LanguageTool process manager
            metrics: Prometheus metrics dictionary for instrumentation
        """
        self.settings = settings
        self.manager = manager
        self.metrics = metrics
        self.semaphore = asyncio.Semaphore(settings.LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS)
        self.server_url = f"http://localhost:{settings.LANGUAGE_TOOL_PORT}"

        # Create a dedicated HTTP session for LanguageTool communication
        self.http_session: aiohttp.ClientSession | None = None

        logger.info(
            "LanguageToolWrapper initialized",
            extra={
                "server_url": self.server_url,
                "max_concurrent": settings.LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS,
                "timeout": settings.LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS,
            },
        )

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure HTTP session is initialized."""
        if not self.http_session:
            self.http_session = aiohttp.ClientSession()
        return self.http_session

    async def check_text(
        self, text: str, correlation_context: CorrelationContext, language: str = "en-US"
    ) -> list[dict[str, Any]]:
        """
        Check text for grammar errors using LanguageTool server.

        Args:
            text: The text to analyze for grammar errors
            correlation_context: Request correlation context for tracing
            language: Language code for analysis (default: en-US)

        Returns:
            List of dictionaries matching GrammarError structure from common_core

        Raises:
            HuleEduError: If grammar analysis fails
        """
        # Limit concurrency to prevent overwhelming the server
        async with self.semaphore:
            logger.debug(
                "Analyzing text for grammar errors",
                extra={
                    "correlation_id": str(correlation_context.uuid),
                    "text_length": len(text),
                    "language": language,
                },
            )

            # Start wrapper timing for metrics
            wrapper_start = time.perf_counter()

            try:
                # Apply timeout to the entire operation
                async with asyncio.timeout(self.settings.LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS):
                    # Call LanguageTool server
                    matches = await self._call_language_tool(text, language, correlation_context)

                    # Filter out spelling/typo categories
                    filtered_matches = self._filter_categories(matches)

                    # Map to GrammarError format
                    grammar_errors = self._map_to_grammar_errors(filtered_matches, text)

                    # Record successful wrapper duration
                    wrapper_duration = time.perf_counter() - wrapper_start
                    if self.metrics and "wrapper_duration_seconds" in self.metrics:
                        self.metrics["wrapper_duration_seconds"].labels(language=language).observe(
                            wrapper_duration
                        )

                    logger.info(
                        "Grammar analysis completed",
                        extra={
                            "correlation_id": str(correlation_context.uuid),
                            "total_matches": len(matches),
                            "filtered_matches": len(filtered_matches),
                            "grammar_errors": len(grammar_errors),
                        },
                    )

                    return grammar_errors

            except asyncio.TimeoutError:
                # Record failed wrapper duration for timeout
                wrapper_duration = time.perf_counter() - wrapper_start
                if self.metrics and "wrapper_duration_seconds" in self.metrics:
                    self.metrics["wrapper_duration_seconds"].labels(language=language).observe(
                        wrapper_duration
                    )

                logger.error(
                    "LanguageTool request timed out",
                    extra={
                        "correlation_id": str(correlation_context.uuid),
                        "timeout_seconds": self.settings.LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS,
                    },
                )
                raise_timeout_error(
                    service="language_tool_service",
                    operation="check_text",
                    timeout_seconds=self.settings.LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS,
                    message="LanguageTool request timed out",
                    correlation_id=correlation_context.uuid,
                )
            except aiohttp.ClientError as e:
                # Record failed wrapper duration for client error
                wrapper_duration = time.perf_counter() - wrapper_start
                if self.metrics and "wrapper_duration_seconds" in self.metrics:
                    self.metrics["wrapper_duration_seconds"].labels(language=language).observe(
                        wrapper_duration
                    )

                logger.error(
                    f"HTTP client error communicating with LanguageTool: {e}",
                    extra={"correlation_id": str(correlation_context.uuid)},
                    exc_info=True,
                )
                raise_external_service_error(
                    service="language_tool_service",
                    operation="check_text",
                    external_service="languagetool_server",
                    message=f"Failed to communicate with LanguageTool server: {str(e)}",
                    correlation_id=correlation_context.uuid,
                )
            except Exception as e:
                # Record failed wrapper duration for general error
                wrapper_duration = time.perf_counter() - wrapper_start
                if self.metrics and "wrapper_duration_seconds" in self.metrics:
                    self.metrics["wrapper_duration_seconds"].labels(language=language).observe(
                        wrapper_duration
                    )

                logger.error(
                    f"Unexpected error during grammar analysis: {e}",
                    extra={"correlation_id": str(correlation_context.uuid)},
                    exc_info=True,
                )
                # Check if we need to restart the server
                if not await self.manager.health_check():
                    logger.warning("Server health check failed, attempting restart")
                    try:
                        await self.manager.restart_if_needed()
                    except Exception as restart_error:
                        logger.error(f"Failed to restart LanguageTool server: {restart_error}")

                raise_service_unavailable(
                    service="language_tool_service",
                    operation="check_text",
                    unavailable_service="languagetool_server",
                    message=f"Grammar analysis failed: {str(e)}",
                    correlation_id=correlation_context.uuid,
                )

    async def _call_language_tool(
        self, text: str, language: str, correlation_context: CorrelationContext
    ) -> list[dict[str, Any]]:
        """
        Make HTTP request to LanguageTool server.

        Args:
            text: Text to check
            language: Language code
            correlation_context: Request correlation context

        Returns:
            List of matches from LanguageTool
        """
        session = await self._ensure_session()

        # Convert language code format (en-US -> en-US, en -> en-US)
        if language == "en":
            language = "en-US"
        elif language == "sv":
            language = "sv"

        # Prepare request data
        data = {
            "text": text,
            "language": language,
            "enabledOnly": "false",  # Get all rules
        }

        try:
            async with session.post(
                f"{self.server_url}/v2/check",
                data=data,  # LanguageTool expects form data, not JSON
                timeout=aiohttp.ClientTimeout(
                    total=self.settings.LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS - 1
                ),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        f"LanguageTool returned error status: {response.status}",
                        extra={
                            "correlation_id": str(correlation_context.uuid),
                            "status": response.status,
                            "error": error_text[:500],  # Truncate long errors
                        },
                    )
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status,
                        message=f"LanguageTool error: {error_text[:200]}",
                    )

                result = await response.json()
                matches: list[dict[str, Any]] = result.get("matches", [])
                return matches

        except json.JSONDecodeError as e:
            logger.error(
                f"Failed to parse LanguageTool response: {e}",
                extra={"correlation_id": str(correlation_context.uuid)},
            )
            raise ValueError(f"Invalid JSON response from LanguageTool: {str(e)}")

    def _filter_categories(self, matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Filter out spelling and typo categories.

        Args:
            matches: Raw matches from LanguageTool

        Returns:
            Filtered list containing only grammar-related matches
        """
        filtered = []

        for match in matches:
            # Allow all categories through so spelling data can be aggregated downstream.
            # Only drop irrelevant whitespace-only findings to avoid noisy responses.
            issue_type = match.get("rule", {}).get("issueType", "")
            if isinstance(issue_type, str) and issue_type.lower() == "whitespace":
                logger.debug("Filtering out whitespace-only issue")
                continue

            filtered.append(match)

        return filtered

    def _map_to_grammar_errors(
        self, matches: list[dict[str, Any]], original_text: str
    ) -> list[dict[str, Any]]:
        """
        Map LanguageTool matches to GrammarError format.

        Args:
            matches: Filtered LanguageTool matches
            original_text: The original text for context extraction

        Returns:
            List of GrammarError-compatible dictionaries
        """
        errors = []

        for match in matches:
            # Extract basic information
            rule = match.get("rule", {})
            category = rule.get("category", {})
            context = match.get("context", {})

            # Calculate offset and length
            offset = match.get("offset", 0)
            length = match.get("length", 0)

            # Extract replacements
            replacements = []
            for replacement in match.get("replacements", []):
                if isinstance(replacement, dict):
                    replacements.append(replacement.get("value", ""))
                else:
                    replacements.append(str(replacement))

            # Extract context information
            context_text = context.get("text", "")
            context_offset = context.get("offset", 0)

            # If context is not provided by LanguageTool, extract it ourselves
            if not context_text and original_text:
                # Create a context window (40 chars before, 40 chars after)
                context_start = max(0, offset - 40)
                context_end = min(len(original_text), offset + length + 40)
                context_text = original_text[context_start:context_end]
                context_offset = offset - context_start

            # Map severity
            severity = "info"
            issue_type = rule.get("issueType", "").lower()
            if issue_type in ["grammar", "inconsistency"]:
                severity = "warning"
            elif issue_type in ["error", "incorrect"]:
                severity = "error"

            # Build GrammarError-compatible dictionary
            error = {
                # Original GrammarError fields
                "rule_id": rule.get("id", "UNKNOWN"),
                "message": match.get("message", ""),
                "short_message": match.get("shortMessage", match.get("message", "")[:50]),
                "offset": offset,
                "length": length,
                "replacements": replacements[:5],  # Limit replacements
                "category": category.get("name", "unknown"),
                "severity": severity,
                # Enhanced fields from TASK-052A
                "category_id": category.get("id", "UNKNOWN"),
                "category_name": category.get("name", "Unknown"),
                "context": context_text,
                "context_offset": context_offset,
            }

            errors.append(error)

        return errors

    async def get_health_status(self, correlation_context: CorrelationContext) -> dict[str, Any]:
        """
        Check the health status of the Language Tool wrapper.

        Args:
            correlation_context: Request correlation context for tracing

        Returns:
            Health status information including server status
        """
        logger.debug(
            "Health check requested",
            extra={"correlation_id": str(correlation_context.uuid)},
        )

        # Get manager status
        manager_status = self.manager.get_status()

        # Check if server is healthy
        is_healthy = await self.manager.health_check()

        # Measure response time
        response_time_ms = 0
        if is_healthy:
            try:
                start = time.time()
                session = await self._ensure_session()
                async with session.get(
                    f"{self.server_url}/v2/languages",
                    timeout=aiohttp.ClientTimeout(total=2),
                ) as response:
                    if response.status == 200:
                        response_time_ms = int((time.time() - start) * 1000)
            except Exception:
                is_healthy = False

        health_payload = {
            "implementation": "production",
            "status": "healthy" if is_healthy else "unhealthy",
            "response_time_ms": response_time_ms,
            "server": manager_status,
            "note": "LanguageTool server with grammar filtering",
        }

        if not is_healthy:
            health_payload["recent_output"] = self.manager.get_recent_output()

        return health_payload

    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.http_session:
            await self.http_session.close()
            self.http_session = None
