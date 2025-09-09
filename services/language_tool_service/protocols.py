"""
Protocol definitions for Language Tool Service dependency injection.

This module defines behavioral contracts using typing.Protocol for all
Language Tool Service dependencies to enable clean architecture and testability.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID


class LanguageToolWrapperProtocol(Protocol):
    """Protocol for Language Tool grammar categorization service."""

    async def check_text(
        self, text: str, correlation_id: UUID, language: str = "en-US"
    ) -> list[dict[str, Any]]:
        """
        Check text for grammar and spelling errors.

        Args:
            text: The text to analyze for grammar errors
            correlation_id: Request correlation ID for tracing
            language: Language code for analysis (default: en-US)

        Returns:
            List of grammar error objects with categorization information

        Raises:
            HuleEduError: If grammar analysis fails

        Note:
            This is a temporary stub implementation. Will be replaced with
            actual Language Tool integration in future iterations.
        """
        ...

    async def get_health_status(self, correlation_id: UUID) -> dict[str, Any]:
        """
        Check the health status of the Language Tool wrapper.

        Args:
            correlation_id: Request correlation ID for tracing

        Returns:
            Health status information including availability and response times

        Raises:
            HuleEduError: If health check fails
        """
        ...
