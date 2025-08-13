"""Language Tool Service client implementation - SKELETON."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from uuid import UUID

import aiohttp
from common_core.events.nlp_events import GrammarAnalysis, GrammarError
from huleedu_service_libs.logging_utils import create_service_logger

from services.nlp_service.protocols import LanguageToolClientProtocol

if TYPE_CHECKING:
    pass

logger = create_service_logger("nlp_service.implementations.language_tool_client")


class LanguageToolServiceClient(LanguageToolClientProtocol):
    """Client for Language Tool Service integration - SKELETON implementation.

    This skeleton provides mock responses for development and testing.
    Will be replaced with actual HTTP client implementation when Language Tool Service is ready.
    """

    def __init__(self, language_tool_service_url: str) -> None:
        """Initialize client with service URL.

        Args:
            language_tool_service_url: Base URL for Language Tool Service
        """
        self.service_url = language_tool_service_url.rstrip("/")
        logger.info(
            f"LanguageToolServiceClient initialized (skeleton) with URL: {self.service_url}"
        )

    async def check_grammar(
        self,
        text: str,
        http_session: aiohttp.ClientSession,
        correlation_id: UUID,
        language: str = "auto",
    ) -> GrammarAnalysis:
        """Check grammar using Language Tool Service - SKELETON implementation.

        This skeleton returns mock data for testing the flow.

        Args:
            text: The text to check for grammar errors
            http_session: HTTP session for external API calls
            correlation_id: Correlation ID for tracking
            language: Language code ("en", "sv") or "auto"

        Returns:
            GrammarAnalysis with mock errors for testing
        """
        start_time = time.time()

        logger.debug(
            "Checking grammar for text (skeleton mode)",
            extra={
                "correlation_id": str(correlation_id),
                "text_length": len(text),
                "language": language,
            },
        )

        # TODO: Implement actual HTTP call to Language Tool Service
        # Expected implementation:
        # 1. Prepare request payload with text and language
        # 2. Make POST request to language_tool_service_url/check endpoint
        # 3. Parse response into GrammarError objects
        # 4. Handle various error cases with structured error handling

        # Example of what the real implementation would look like:
        """
        try:
            url = f"{self.service_url}/v1/check"
            payload = {
                "text": text,
                "language": language if language != "auto" else None,
            }
            headers = {
                "X-Correlation-ID": str(correlation_id),
                "Content-Type": "application/json",
            }

            async with http_session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise_external_service_error(
                        service="nlp_service",
                        operation="check_grammar",
                        external_service="language_tool_service",
                        message=f"Language Tool Service returned {response.status}: {error_text}",
                        correlation_id=correlation_id,
                        status_code=response.status,
                    )

                result = await response.json()
                # Parse result into GrammarError objects
                errors = [
                    GrammarError(
                        rule_id=error["ruleId"],
                        message=error["message"],
                        short_message=error.get("shortMessage", ""),
                        offset=error["offset"],
                        length=error["length"],
                        replacements=error.get("replacements", []),
                        category=error.get("category", "unknown"),
                        severity=error.get("severity", "info"),
                    )
                    for error in result.get("matches", [])
                ]

        except aiohttp.ClientError as e:
            raise_external_service_error(
                service="nlp_service",
                operation="check_grammar",
                external_service="language_tool_service",
                message=f"Failed to connect to Language Tool Service: {str(e)}",
                correlation_id=correlation_id,
            )
        """

        # SKELETON: Generate mock grammar errors for testing
        mock_errors = []

        # Add a mock error if text contains common issues (for testing)
        text_lower = text.lower()

        if "their" in text_lower and "there" in text_lower:
            # Mock a their/there confusion error
            mock_errors.append(
                GrammarError(
                    rule_id="CONFUSION_RULE",
                    message="Possible confusion between 'their' and 'there'",
                    short_message="Word confusion",
                    offset=text_lower.index("their"),
                    length=5,
                    replacements=["there"],
                    category="grammar",
                    severity="warning",
                )
            )

        if "  " in text:
            # Mock a double space error
            mock_errors.append(
                GrammarError(
                    rule_id="DOUBLE_SPACE",
                    message="Double space detected",
                    short_message="Extra space",
                    offset=text.index("  "),
                    length=2,
                    replacements=[" "],
                    category="typography",
                    severity="info",
                )
            )

        # Calculate processing time
        processing_time_ms = int((time.time() - start_time) * 1000)

        # Determine actual language (mock detection)
        detected_language = language if language != "auto" else "en"

        logger.info(
            f"Grammar check completed (skeleton): {len(mock_errors)} errors found",
            extra={
                "correlation_id": str(correlation_id),
                "error_count": len(mock_errors),
                "language": detected_language,
                "processing_time_ms": processing_time_ms,
            },
        )

        return GrammarAnalysis(
            error_count=len(mock_errors),
            errors=mock_errors,
            language=detected_language,
            processing_time_ms=processing_time_ms,
        )
