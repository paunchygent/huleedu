"""
Protocol definitions for File Service dependency injection.

This module defines behavioral contracts using typing.Protocol for all
File Service dependencies to enable clean architecture and testability.
"""

from __future__ import annotations

import uuid
from typing import Optional, Protocol

from common_core.events.file_events import EssayContentProvisionedV1


class ContentServiceClientProtocol(Protocol):
    """Protocol for HTTP client interactions with Content Service."""

    async def store_content(self, content_bytes: bytes) -> str:
        """
        Store content in Content Service and return storage ID.

        Args:
            content_bytes: Raw binary content to store

        Returns:
            storage_id: Unique identifier for stored content

        Note:
            Aligned with current Content Service API (POST /v1/content)
            which accepts raw binary data.
        """
        ...


class EventPublisherProtocol(Protocol):
    """Protocol for publishing Kafka events."""

    async def publish_essay_content_provisioned(
        self, event_data: EssayContentProvisionedV1, correlation_id: Optional[uuid.UUID]
    ) -> None:
        """
        Publish EssayContentProvisionedV1 event to Kafka.

        Args:
            event_data: EssayContentProvisionedV1 event payload
            correlation_id: Optional correlation ID for request tracing
        """
        ...


class TextExtractorProtocol(Protocol):
    """Protocol for text extraction from file content."""

    async def extract_text(self, file_content: bytes, file_name: str) -> str:
        """
        Extract text content from file bytes.

        Args:
            file_content: Raw file bytes
            file_name: Original filename for type dispatch/context

        Returns:
            Extracted text content as string

        Note:
            file_name can be used for context or simple type dispatch
        """
        ...
