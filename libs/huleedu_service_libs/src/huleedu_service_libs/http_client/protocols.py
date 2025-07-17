"""HTTP client protocol definitions for HuleEdu services.

This module defines the protocol interfaces for HTTP client operations,
following HuleEdu's protocol-based architecture patterns.
"""

from typing import Any, Protocol
from uuid import UUID

from common_core.domain_enums import ContentType


class HttpClientProtocol(Protocol):
    """Base protocol for HTTP client operations with structured error handling.

    This protocol defines the fundamental HTTP operations that all services
    need, with standardized error handling and correlation ID tracking.
    """

    async def get(
        self,
        url: str,
        correlation_id: UUID,
        timeout_seconds: int = 10,
        headers: dict[str, str] | None = None,
        **context: Any,
    ) -> str:
        """Execute GET request with structured error handling.

        Args:
            url: Target URL for the GET request
            correlation_id: Request correlation ID for tracing
            timeout_seconds: Request timeout in seconds
            headers: Optional HTTP headers
            **context: Additional context for error reporting

        Returns:
            Response body as string

        Raises:
            HuleEduError: On any HTTP error, timeout, or connection issue
        """
        ...

    async def post(
        self,
        url: str,
        data: bytes | str,
        correlation_id: UUID,
        timeout_seconds: int = 10,
        headers: dict[str, str] | None = None,
        **context: Any,
    ) -> dict[str, Any]:
        """Execute POST request with structured error handling.

        Args:
            url: Target URL for the POST request
            data: Request body data (bytes or string)
            correlation_id: Request correlation ID for tracing
            timeout_seconds: Request timeout in seconds
            headers: Optional HTTP headers
            **context: Additional context for error reporting

        Returns:
            Response body parsed as JSON dict

        Raises:
            HuleEduError: On any HTTP error, timeout, or connection issue
        """
        ...


class ContentServiceClientProtocol(Protocol):
    """Protocol for Content Service specific HTTP operations.

    This protocol defines the standard Content Service operations that
    multiple services need to perform, with consistent error handling
    and response parsing.
    """

    async def fetch_content(
        self,
        storage_id: str,
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> str:
        """Fetch content by storage ID from Content Service.

        Args:
            storage_id: Content storage identifier
            correlation_id: Request correlation ID for tracing
            essay_id: Optional essay ID for logging context

        Returns:
            Content text

        Raises:
            HuleEduError: On fetch failure, content not found, or service error
        """
        ...

    async def store_content(
        self,
        content: str,
        content_type: ContentType,
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> str:
        """Store content to Content Service and return storage ID.

        Args:
            content: Content text to store
            content_type: Type of content being stored
            correlation_id: Request correlation ID for tracing
            essay_id: Optional essay ID for logging context

        Returns:
            New storage ID for the stored content

        Raises:
            HuleEduError: On storage failure or invalid response
        """
        ...
