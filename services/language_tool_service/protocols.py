"""
Protocol definitions for Language Tool Service dependency injection.

This module defines behavioral contracts using typing.Protocol for all
Language Tool Service dependencies to enable clean architecture and testability.
"""

from __future__ import annotations

from typing import Any, Protocol

from huleedu_service_libs.error_handling.correlation import CorrelationContext


class LanguageToolWrapperProtocol(Protocol):
    """Protocol for Language Tool grammar categorization service."""

    async def check_text(
        self, text: str, correlation_context: CorrelationContext, language: str = "en-US"
    ) -> list[dict[str, Any]]:
        """
        Check text for grammar and spelling errors.

        Args:
            text: The text to analyze for grammar errors
            correlation_context: Request correlation context for tracing
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

    async def get_health_status(self, correlation_context: CorrelationContext) -> dict[str, Any]:
        """
        Check the health status of the Language Tool wrapper.

        Args:
            correlation_context: Request correlation context for tracing

        Returns:
            Health status information including availability and response times

        Raises:
            HuleEduError: If health check fails
        """
        ...

class LanguageToolManagerProtocol(Protocol):
    """Protocol for Language Tool manager process lifecycle."""

    async def start(self) -> None:
        """
        Start the LanguageTool server process.
        
        Raises:
            HuleEduError: If the server fails to start
        """
        ...

    async def stop(self) -> None:
        """Gracefully stop the LanguageTool server process."""
        ...

    async def health_check(self) -> bool:
        """
        Check if the LanguageTool server is healthy.
        
        Returns:
            True if the server is responsive, False otherwise
        """
        ...

    async def restart_if_needed(self) -> None:
        """
        Restart the server if it's not healthy.
        
        Implements exponential backoff to prevent restart loops.
        """
        ...

    def get_status(self) -> dict[str, Any]:
        """
        Get the current status of the LanguageTool server.
        
        Returns:
            Dictionary with server status information
        """
        ...

    async def get_jvm_heap_usage(self) -> int | None:
        """
        Get current JVM heap usage in MB.
        
        Returns:
            Heap usage in MB, or None if unable to retrieve
        """
        ...
