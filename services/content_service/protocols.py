"""
Content Service behavioral contracts and protocols.

This module defines the protocols (interfaces) that Content Service components
must implement, enabling dependency injection and testability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from common_core.observability_enums import OperationType
from common_core.status_enums import OperationStatus


class ContentStoreProtocol(Protocol):
    """Protocol for content storage operations."""

    async def save_content(self, content_data: bytes) -> str:
        """
        Save content data and return storage identifier.

        Args:
            content_data: Raw bytes to store

        Returns:
            Storage identifier (UUID hex string)

        Raises:
            Exception: If storage operation fails
        """
        ...

    async def get_content_path(self, content_id: str) -> Path:
        """
        Get file path for content identifier.

        Args:
            content_id: Storage identifier

        Returns:
            Path to content file
        """
        ...

    async def content_exists(self, content_id: str) -> bool:
        """
        Check if content exists for given identifier.

        Args:
            content_id: Storage identifier

        Returns:
            True if content exists, False otherwise
        """
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
