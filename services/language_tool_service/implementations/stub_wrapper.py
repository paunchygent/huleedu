"""
Stub implementation of Language Tool wrapper for development and testing.

This module provides a temporary stub implementation that simulates Language Tool
behavior for development purposes. Will be replaced with actual Language Tool
integration in future iterations.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger

from services.language_tool_service.config import Settings
from services.language_tool_service.protocols import LanguageToolWrapperProtocol

logger = create_service_logger("language_tool_service.implementations.stub_wrapper")


class StubLanguageToolWrapper(LanguageToolWrapperProtocol):
    """
    Stub implementation of Language Tool wrapper.

    This implementation provides predictable responses for development and testing
    without requiring actual Language Tool integration.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize stub wrapper with settings.

        Args:
            settings: Service configuration settings
        """
        self.settings = settings
        logger.info("StubLanguageToolWrapper initialized")

    async def check_text(
        self, text: str, correlation_id: UUID, language: str = "en-US"
    ) -> list[dict[str, Any]]:
        """
        Simulate text checking for grammar and spelling errors.

        Returns predictable stub data based on text patterns for testing.

        Args:
            text: The text to analyze for grammar errors
            correlation_id: Request correlation ID for tracing
            language: Language code for analysis (default: en-US)

        Returns:
            List of dictionaries matching GrammarError structure from common_core
        """
        logger.debug(
            "Analyzing text for grammar errors (stub mode)",
            correlation_id=str(correlation_id),
            text_length=len(text),
        )

        # Simulate different responses based on text content
        errors = []

        # Simple pattern matching for demonstration
        # Return GrammarError-compatible dictionaries (from common_core.events.nlp_events)
        if "there" in text.lower() and "their" not in text.lower():
            offset = text.lower().find("there")
            context_start = max(0, offset - 20)
            context_end = min(len(text), offset + 25)
            context = text[context_start:context_end]
            
            errors.append(
                {
                    # Original GrammarError fields
                    "rule_id": "THERE_THEIR_CONFUSION",
                    "message": "Possible confusion of 'there' and 'their'",
                    "short_message": "Word confusion",
                    "offset": offset,
                    "length": 5,
                    "replacements": ["their"],
                    "category": "GRAMMAR",
                    "severity": "warning",
                    # New enhanced fields from TASK-052A
                    "category_id": "CONFUSED_WORDS",
                    "category_name": "Confused Words",
                    "context": context,
                    "context_offset": offset - context_start,
                }
            )

        if "recieve" in text.lower():
            offset = text.lower().find("recieve")
            context_start = max(0, offset - 20)
            context_end = min(len(text), offset + 25)
            context = text[context_start:context_end]
            
            errors.append(
                {
                    # Original GrammarError fields
                    "rule_id": "IE_EI_SPELLING",
                    "message": "Spelling error: 'recieve' should be 'receive'",
                    "short_message": "Spelling error",
                    "offset": offset,
                    "length": 7,
                    "replacements": ["receive"],
                    "category": "TYPOS",  # This would be filtered in real implementation
                    "severity": "error",
                    # New enhanced fields from TASK-052A
                    "category_id": "TYPOS",
                    "category_name": "Typographical Errors",
                    "context": context,
                    "context_offset": offset - context_start,
                }
            )

        logger.info(
            "Grammar analysis completed (stub mode)",
            correlation_id=str(correlation_id),
            error_count=len(errors),
        )

        return errors

    async def get_health_status(self, correlation_id: UUID) -> dict[str, Any]:
        """
        Return stub health status.

        Args:
            correlation_id: Request correlation ID for tracing

        Returns:
            Health status information for stub implementation
        """
        logger.debug("Health check requested (stub mode)", correlation_id=str(correlation_id))

        return {
            "implementation": "stub",
            "response_time_ms": 1,
            "status": "healthy",
            "note": "This is a stub implementation for development",
        }
