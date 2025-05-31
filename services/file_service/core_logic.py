"""
Core business logic for File Service file processing workflow.

This module implements the main file processing pipeline that coordinates
text extraction, content storage, and event publishing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from huleedu_service_libs.logging_utils import create_service_logger
from protocols import (
    ContentServiceClientProtocol,
    EventPublisherProtocol,
    TextExtractorProtocol,
)
from text_processing import parse_student_info

from common_core.enums import ContentType, ProcessingEvent
from common_core.events.batch_coordination_events import EssayContentReady
from common_core.metadata_models import (
    EntityReference,
    StorageReferenceMetadata,
    SystemProcessingMetadata,
)

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
    1. Generate unique essay ID
    2. Extract text content from file
    3. Parse student information (stubbed)
    4. Store content via Content Service
    5. Construct and publish EssayContentReady event

    Args:
        batch_id: Batch identifier this file belongs to
        file_content: Raw file bytes
        file_name: Original filename
        main_correlation_id: Correlation ID for batch upload operation
        text_extractor: Text extraction protocol implementation
        content_client: Content Service client protocol implementation
        event_publisher: Event publishing protocol implementation

    Returns:
        Dict containing processing result with essay_id, file_name, and status
    """
    essay_id = str(uuid.uuid4())
    logger.info(
        f"Processing file {file_name} for batch {batch_id}, essay {essay_id}",
        extra={"correlation_id": str(main_correlation_id)}
    )

    try:
        # Extract text content from file
        text = await text_extractor.extract_text(file_content, file_name)
        if not text:
            logger.warning(
                f"Text extraction failed or returned empty for {file_name}, essay {essay_id}",
                extra={"correlation_id": str(main_correlation_id)}
            )
            return {
                "essay_id": essay_id,
                "file_name": file_name,
                "status": "extraction_failed_or_empty"
            }

        # Parse student information (stubbed in walking skeleton)
        student_name, student_email = await parse_student_info(text)

        # Store extracted text content via Content Service
        storage_id = await content_client.store_content(text.encode('utf-8'))
        logger.info(
            f"Stored content for essay {essay_id}, storage_id: {storage_id}",
            extra={"correlation_id": str(main_correlation_id)}
        )

        # Construct StorageReferenceMetadata
        content_storage_ref = StorageReferenceMetadata()
        content_storage_ref.add_reference(ContentType.ORIGINAL_ESSAY, storage_id)

        # Construct EntityReference and SystemProcessingMetadata
        essay_entity_ref = EntityReference(
            entity_id=essay_id,
            entity_type="essay",
            parent_id=batch_id
        )
        event_sys_metadata = SystemProcessingMetadata(
            entity=essay_entity_ref,
            event=ProcessingEvent.ESSAY_CONTENT_READY.value,
            timestamp=datetime.now(timezone.utc)
        )

        # Construct EssayContentReady event data
        essay_ready_event_data = EssayContentReady(
            essay_id=essay_id,
            batch_id=batch_id,
            content_storage_reference=content_storage_ref,
            entity=essay_entity_ref,
            metadata=event_sys_metadata,
            student_name=student_name,  # Will be None from stub
            student_email=student_email  # Will be None from stub
        )

        # Publish the event
        await event_publisher.publish_essay_content_ready(
            essay_ready_event_data,
            main_correlation_id
        )
        logger.info(
            f"Published EssayContentReady for essay {essay_id}",
            extra={"correlation_id": str(main_correlation_id)}
        )

        return {
            "essay_id": essay_id,
            "file_name": file_name,
            "status": "processing_initiated"
        }

    except Exception as e:
        logger.error(
            f"Error processing file {file_name} for essay {essay_id}: {e}",
            extra={"correlation_id": str(main_correlation_id)},
            exc_info=True
        )
        return {
            "essay_id": essay_id,
            "file_name": file_name,
            "status": "processing_error",
            "detail": str(e)
        }
