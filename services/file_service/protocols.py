"""
Protocol definitions for File Service dependency injection.

This module defines behavioral contracts using typing.Protocol for all
File Service dependencies to enable clean architecture and testability.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from common_core.enums import ContentType
from common_core.events.file_events import EssayContentProvisionedV1, EssayValidationFailedV1
from services.file_service.validation_models import ValidationResult


class ContentServiceClientProtocol(Protocol):
    """Protocol for HTTP client interactions with Content Service."""

    async def store_content(self, content_bytes: bytes, content_type: ContentType) -> str:
        """
        Store content in Content Service and return storage ID.

        Args:
            content_bytes: Raw binary content to store
            content_type: Type of content being stored (RAW_UPLOAD_BLOB, EXTRACTED_PLAINTEXT, etc.)

        Returns:
            storage_id: Unique identifier for stored content

        Note:
            Updated to support ContentType for pre-emptive raw file storage.
            Enables differentiation between raw file blobs and processed text content.
        """
        ...


class EventPublisherProtocol(Protocol):
    """Protocol for publishing Kafka events."""

    async def publish_essay_content_provisioned(
        self, event_data: EssayContentProvisionedV1, correlation_id: uuid.UUID | None,
    ) -> None:
        """
        Publish EssayContentProvisionedV1 event to Kafka.

        Args:
            event_data: EssayContentProvisionedV1 event payload
            correlation_id: Optional correlation ID for request tracing
        """
        ...

    async def publish_essay_validation_failed(
        self, event_data: EssayValidationFailedV1, correlation_id: uuid.UUID | None,
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


class ContentValidatorProtocol(Protocol):
    """Protocol for validating extracted file content."""

    async def validate_content(self, text: str, file_name: str) -> ValidationResult:
        """
        Validate extracted text content against business rules.

        Args:
            text: Extracted text content to validate
            file_name: Original filename for context in error messages

        Returns:
            ValidationResult indicating success/failure with details
        """
        ...
