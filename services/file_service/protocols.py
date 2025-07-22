"""
Protocol definitions for File Service dependency injection.

This module defines behavioral contracts using typing.Protocol for all
File Service dependencies to enable clean architecture and testability.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from common_core.domain_enums import ContentType
from common_core.events.file_events import EssayContentProvisionedV1, EssayValidationFailedV1
from common_core.events.file_management_events import BatchFileAddedV1, BatchFileRemovedV1


class ContentServiceClientProtocol(Protocol):
    """Protocol for HTTP client interactions with Content Service."""

    async def store_content(
        self, content_bytes: bytes, content_type: ContentType, correlation_id: UUID
    ) -> str:
        """
        Store content in Content Service and return storage ID.

        Args:
            content_bytes: Raw binary content to store
            content_type: Type of content being stored (RAW_UPLOAD_BLOB, EXTRACTED_PLAINTEXT, etc.)
            correlation_id: Request correlation ID for tracing

        Returns:
            storage_id: Unique identifier for stored content

        Raises:
            HuleEduError: If storage operation fails

        Note:
            Updated to support ContentType for pre-emptive raw file storage.
            Enables differentiation between raw file blobs and processed text content.
        """
        ...


class EventPublisherProtocol(Protocol):
    """Protocol for publishing Kafka events."""

    async def publish_essay_content_provisioned(
        self,
        event_data: EssayContentProvisionedV1,
        correlation_id: UUID,
    ) -> None:
        """
        Publish EssayContentProvisionedV1 event to Kafka.

        Args:
            event_data: EssayContentProvisionedV1 event payload
            correlation_id: Optional correlation ID for request tracing
        """
        ...

    async def publish_essay_validation_failed(
        self,
        event_data: EssayValidationFailedV1,
        correlation_id: UUID,
    ) -> None:
        """
        Publish EssayValidationFailedV1 event to Kafka.

        Args:
            event_data: EssayValidationFailedV1 event payload
            correlation_id: Optional correlation ID for request tracing

        Note:
            Critical for BOS/ELS coordination - enables ELS to adjust
            slot expectations when validation prevents content storage.
        """
        ...

    async def publish_batch_file_added_v1(
        self,
        event_data: BatchFileAddedV1,
        correlation_id: UUID,
    ) -> None:
        """
        Publish BatchFileAddedV1 event to Kafka.

        Args:
            event_data: BatchFileAddedV1 event payload
            correlation_id: Optional correlation ID for request tracing
        """
        ...

    async def publish_batch_file_removed_v1(
        self,
        event_data: BatchFileRemovedV1,
        correlation_id: UUID,
    ) -> None:
        """
        Publish BatchFileRemovedV1 event to Kafka.

        Args:
            event_data: BatchFileRemovedV1 event payload
            correlation_id: Optional correlation ID for request tracing
        """
        ...


class TextExtractorProtocol(Protocol):
    """Protocol for text extraction from file content."""

    async def extract_text(self, file_content: bytes, file_name: str, correlation_id: UUID) -> str:
        """
        Extract text content from file bytes.

        Args:
            file_content: Raw file bytes
            file_name: Original filename for type dispatch/context
            correlation_id: Request correlation ID for tracing

        Returns:
            Extracted text content as string

        Raises:
            HuleEduError: If extraction fails

        Note:
            file_name can be used for context or simple type dispatch
        """
        ...


class ContentValidatorProtocol(Protocol):
    """Protocol for validating extracted file content."""

    async def validate_content(self, text: str, file_name: str, correlation_id: UUID) -> None:
        """
        Validate extracted text content against business rules.

        Args:
            text: Extracted text content to validate
            file_name: Original filename for context in error messages
            correlation_id: Request correlation ID for tracing

        Returns:
            None if validation passes

        Raises:
            HuleEduError: If validation fails with specific error code
        """
        ...


class BatchStateValidatorProtocol(Protocol):
    """Protocol for validating batch state and modification permissions."""

    async def can_modify_batch_files(
        self, batch_id: str, user_id: str, correlation_id: UUID
    ) -> None:
        """
        Check if batch files can be modified.

        Args:
            batch_id: The batch identifier
            user_id: The authenticated user identifier
            correlation_id: Request correlation ID for tracing

        Returns:
            None if modification is allowed

        Raises:
            HuleEduError: If batch cannot be modified with specific reason
        """
        ...

    async def get_batch_lock_status(self, batch_id: str, correlation_id: UUID) -> dict[str, Any]:
        """
        Get detailed batch lock status information.

        Args:
            batch_id: The batch identifier
            correlation_id: Request correlation ID for tracing

        Returns:
            dict: Lock status with reason and metadata

        Raises:
            HuleEduError: If batch status cannot be retrieved
        """
        ...
