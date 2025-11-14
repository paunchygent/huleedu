"""
Content Service behavioral contracts and protocols.

This module defines the protocols (interfaces) that Content Service components
must implement, enabling dependency injection and testability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import UUID

from common_core.observability_enums import OperationType
from common_core.status_enums import OperationStatus


class ContentStoreProtocol(Protocol):
    """Protocol for content storage operations."""

    async def save_content(self, content_data: bytes, correlation_id: UUID) -> str:
        """
        Save content data and return storage identifier.

        Args:
            content_data: Raw bytes to store
            correlation_id: Request correlation ID for tracing

        Returns:
            Storage identifier (UUID hex string)

        Raises:
            HuleEduError: If storage operation fails
        """
        ...

    async def get_content_path(self, content_id: str, correlation_id: UUID) -> Path:
        """
        Get file path for content identifier.

        Args:
            content_id: Storage identifier
            correlation_id: Request correlation ID for tracing

        Returns:
            Path to content file

        Raises:
            HuleEduError: If content not found
        """
        ...

    async def content_exists(self, content_id: str, correlation_id: UUID) -> bool:
        """
        Check if content exists for given identifier.

        Args:
            content_id: Storage identifier
            correlation_id: Request correlation ID for tracing

        Returns:
            True if content exists, False otherwise
        """
        ...


class ContentRepositoryProtocol(Protocol):
    """Protocol for database-backed content persistence."""

    async def save_content(
        self,
        content_id: str,
        content_data: bytes,
        content_type: str,
        correlation_id: UUID | None = None,
    ) -> None:
        """Persist content bytes and metadata."""
        ...

    async def get_content(
        self,
        content_id: str,
        correlation_id: UUID | None = None,
    ) -> tuple[bytes, str]:
        """Retrieve content bytes and content type."""
        ...

    async def content_exists(self, content_id: str) -> bool:
        """Return True if content exists for the given identifier."""
        ...


@runtime_checkable
class ContentMetricsProtocol(Protocol):
    """Protocol for content service metrics collection."""

    def record_operation(self, operation: OperationType, status: OperationStatus) -> None:
        """
        Record a content operation metric.

        Args:
            operation: Operation type (OperationType enum)
            status: Operation status (OperationStatus enum)
        """
        ...
