"""
Core business logic for File Service file processing workflow.

This module implements the main file processing pipeline that coordinates
text extraction, content storage, and event publishing.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from huleedu_service_libs.logging_utils import create_service_logger
from protocols import (
    ContentServiceClientProtocol,
    EventPublisherProtocol,
    TextExtractorProtocol,
)

from common_core.events.file_events import EssayContentProvisionedV1

logger = create_service_logger("file_service.core_logic")


async def process_single_file_upload(
    batch_id: str,
    file_content: bytes,
    file_name: str,
    main_correlation_id: uuid.UUID,
    text_extractor: TextExtractorProtocol,
    content_client: ContentServiceClientProtocol,
    event_publisher: EventPublisherProtocol,
) -> Dict[str, Any]:
    """
    Process a single file upload within a batch.

    This function implements the complete file processing workflow:
    1. Extract text content from file
    2. Store content via Content Service
    3. Calculate file content hash for integrity
    4. Construct and publish EssayContentProvisionedV1 event
    5. Return processing result

    Args:
        batch_id: Batch identifier this file belongs to
        file_content: Raw file bytes
        file_name: Original filename
        main_correlation_id: Correlation ID for batch upload operation
        text_extractor: Text extraction protocol implementation
        content_client: Content Service client protocol implementation
        event_publisher: Event publishing protocol implementation

    Returns:
        Dict containing processing result with file_name, text_storage_id, and status
    """
    logger.info(
        f"Processing file {file_name} for batch {batch_id}",
        extra={"correlation_id": str(main_correlation_id)},
    )

    try:
        # Extract text content from file
        text = await text_extractor.extract_text(file_content, file_name)
        if not text:
            logger.warning(
                f"Text extraction failed or returned empty for {file_name}",
                extra={"correlation_id": str(main_correlation_id)},
            )
            return {"file_name": file_name, "status": "extraction_failed_or_empty"}

        # Store extracted text content via Content Service
        text_storage_id = await content_client.store_content(text.encode("utf-8"))
        logger.info(
            f"Stored content for file {file_name}, text_storage_id: {text_storage_id}",
            extra={"correlation_id": str(main_correlation_id)},
        )

        # Calculate MD5 hash of file content for integrity tracking
        content_md5_hash = hashlib.md5(file_content).hexdigest()
        file_size_bytes = len(file_content)

        # Construct EssayContentProvisionedV1 event data
        content_provisioned_event_data = EssayContentProvisionedV1(
            batch_id=batch_id,
            original_file_name=file_name,
            text_storage_id=text_storage_id,
            file_size_bytes=file_size_bytes,
            content_md5_hash=content_md5_hash,
            correlation_id=main_correlation_id,
            timestamp=datetime.now(timezone.utc),
        )

        # Publish the event
        await event_publisher.publish_essay_content_provisioned(
            content_provisioned_event_data, main_correlation_id
        )
        logger.info(
            f"Published EssayContentProvisionedV1 for file {file_name}",
            extra={"correlation_id": str(main_correlation_id)},
        )

        return {
            "file_name": file_name,
            "text_storage_id": text_storage_id,
            "status": "processing_initiated",
        }

    except Exception as e:
        logger.error(
            f"Error processing file {file_name}: {e}",
            extra={"correlation_id": str(main_correlation_id)},
            exc_info=True,
        )
        return {"file_name": file_name, "status": "processing_error", "detail": str(e)}
