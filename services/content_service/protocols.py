"""
Content Service behavioral contracts and protocols.

This module defines the protocols (interfaces) that Content Service components
must implement, enabling dependency injection and testability.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from common_core.observability_enums import OperationType
from common_core.status_enums import OperationStatus


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
