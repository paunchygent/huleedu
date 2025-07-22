"""
Core business logic for File Service file processing workflow.

This module implements the main file processing pipeline that coordinates
text extraction, content validation, content storage, and event publishing.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from common_core.domain_enums import ContentType
from common_core.error_enums import FileValidationErrorCode
from common_core.events.file_events import EssayContentProvisionedV1, EssayValidationFailedV1
from common_core.status_enums import OperationStatus, ProcessingStatus
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger

from services.file_service.protocols import (
    ContentServiceClientProtocol,
    ContentValidatorProtocol,
    EventPublisherProtocol,
    TextExtractorProtocol,
)

logger = create_service_logger("file_service.core_logic")


async def process_single_file_upload(
    batch_id: str,
    file_content: bytes,
    file_name: str,
    main_correlation_id: uuid.UUID,
    text_extractor: TextExtractorProtocol,
    content_validator: ContentValidatorProtocol,
    content_client: ContentServiceClientProtocol,
    event_publisher: EventPublisherProtocol,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Process a single file upload within a batch using pre-emptive raw storage.

    This function implements the complete file processing workflow:
    1. Store raw file blob immediately (establishes immutable source of truth)
    2. Extract text content from file
    3. Validate extracted content against business rules
    4. If validation passes: Store extracted plaintext and publish success event
    5. If validation fails: Publish validation failure event for BOS/ELS coordination
    6. Return processing result

    Architecture:
    - Pre-emptive raw storage ensures data integrity and reprocessing capability
    - Text extraction handles technical concerns (file format, encoding, corruption)
    - Content validation handles business rules (empty content, length limits, format)
    - Clear separation of concerns ensures consistent error handling and codes

    Args:
        batch_id: Batch identifier this file belongs to
        file_content: Raw file bytes
        file_name: Original filename
        main_correlation_id: Correlation ID for batch upload operation
        text_extractor: Text extraction protocol implementation
        content_validator: Content validation protocol implementation
        content_client: Content Service client protocol implementation
        event_publisher: Event publishing protocol implementation

    Returns:
        Dict containing processing result with file_name, status, and relevant IDs/error info
    """
    logger.info(
        f"Processing file {file_name} for batch {batch_id}",
        extra={"correlation_id": str(main_correlation_id)},
    )

    # Ensure metrics is a usable dictionary even when not provided (e.g., unit tests)
    if metrics is None:
        metrics = {}

    # Step 1: Store raw file blob immediately (pre-emptive storage)
    # This establishes an immutable source of truth before any processing occurs
    try:
        raw_file_storage_id = await content_client.store_content(
            file_content,
            ContentType.RAW_UPLOAD_BLOB,
            main_correlation_id,
        )
        logger.info(
            f"Stored raw file blob for {file_name}, raw_file_storage_id: {raw_file_storage_id}",
            extra={"correlation_id": str(main_correlation_id)},
        )
    except Exception as storage_error:
        logger.error(
            f"Failed to store raw file blob for {file_name}: {storage_error}",
            extra={"correlation_id": str(main_correlation_id)},
            exc_info=True,
        )

        # Publish storage failure event WITHOUT raw_file_storage_id (since storage failed)
        validation_failure_event = EssayValidationFailedV1(
            batch_id=batch_id,
            original_file_name=file_name,
            raw_file_storage_id="STORAGE_FAILED",  # Indicate storage failure
            validation_error_code=FileValidationErrorCode.RAW_STORAGE_FAILED,
            validation_error_message=f"Failed to store raw file: {storage_error}",
            file_size_bytes=len(file_content),
            correlation_id=main_correlation_id,
            timestamp=datetime.now(UTC),
        )

        await event_publisher.publish_essay_validation_failed(
            validation_failure_event,
            main_correlation_id,
        )

        logger.info(
            f"Published EssayValidationFailedV1 for raw storage failure: {file_name}",
            extra={"correlation_id": str(main_correlation_id)},
        )

        # Record metric for raw storage failure
        file_ext = file_name.split(".")[-1].lower() if "." in file_name else "unknown"

        files_uploaded_counter = metrics.get("files_uploaded_total")
        if files_uploaded_counter:
            files_uploaded_counter.labels(
                file_type=file_ext,
                validation_status=OperationStatus.FAILED.value,
                batch_id=str(batch_id),
            ).inc()

        return {
            "file_name": file_name,
            "status": ProcessingStatus.FAILED.value,
            "error_detail": str(storage_error),
        }

    # Step 2: Extract text content from file
    # Note: This should only fail for technical issues (unsupported format, corruption, etc.)
    # Empty files should successfully extract to empty string and be handled by validation
    try:
        text = await text_extractor.extract_text(file_content, file_name, main_correlation_id)
        logger.debug(
            f"Text extraction completed for {file_name}: {len(text) if text else 0} characters",
            extra={"correlation_id": str(main_correlation_id)},
        )
    except HuleEduError as extraction_error:
        logger.error(
            f"Text extraction failed for {file_name}: {extraction_error}",
            extra={"correlation_id": str(main_correlation_id)},
            exc_info=True,
        )

        # Publish technical extraction failure event WITH raw_file_storage_id
        validation_failure_event = EssayValidationFailedV1(
            batch_id=batch_id,
            original_file_name=file_name,
            raw_file_storage_id=raw_file_storage_id,
            validation_error_code=FileValidationErrorCode.TEXT_EXTRACTION_FAILED,
            validation_error_message=extraction_error.error_detail.message,
            file_size_bytes=len(file_content),
            correlation_id=main_correlation_id,
            timestamp=datetime.now(UTC),
        )

        await event_publisher.publish_essay_validation_failed(
            validation_failure_event,
            main_correlation_id,
        )

        logger.info(
            f"Published EssayValidationFailedV1 for technical extraction failure: {file_name}",
            extra={"correlation_id": str(main_correlation_id)},
        )

        # Record metric for text extraction failure
        file_ext = file_name.split(".")[-1].lower() if "." in file_name else "unknown"

        files_uploaded_counter = metrics.get("files_uploaded_total")
        if files_uploaded_counter:
            files_uploaded_counter.labels(
                file_type=file_ext,
                validation_status=OperationStatus.FAILED.value,
                batch_id=str(batch_id),
            ).inc()

        return {
            "file_name": file_name,
            "raw_file_storage_id": raw_file_storage_id,
            "status": ProcessingStatus.FAILED.value,
        }

    # Step 3: Validate extracted content against business rules
    # This handles all content-related issues including empty content, length limits, etc.
    try:
        await content_validator.validate_content(text, file_name, main_correlation_id)
    except HuleEduError as validation_error:
        logger.warning(
            f"Content validation failed for {file_name}: {validation_error.error_detail.message}",
            extra={
                "correlation_id": str(main_correlation_id),
                "error_code": validation_error.error_detail.error_code,
                "error_message": validation_error.error_detail.message,
                "content_length": len(text) if text else 0,
            },
        )

        # Publish business rule validation failure event WITH raw_file_storage_id
        validation_failure_event = EssayValidationFailedV1(
            batch_id=batch_id,
            original_file_name=file_name,
            raw_file_storage_id=raw_file_storage_id,
            validation_error_code=FileValidationErrorCode(validation_error.error_detail.error_code),
            validation_error_message=validation_error.error_detail.message,
            file_size_bytes=len(file_content),
            correlation_id=main_correlation_id,
            timestamp=datetime.now(UTC),
        )

        await event_publisher.publish_essay_validation_failed(
            validation_failure_event,
            main_correlation_id,
        )

        logger.info(
            f"Published EssayValidationFailedV1 for content validation failure: {file_name}",
            extra={"correlation_id": str(main_correlation_id)},
        )

        # Record metric for content validation failure
        file_ext = file_name.split(".")[-1].lower() if "." in file_name else "unknown"

        files_uploaded_counter = metrics.get("files_uploaded_total")
        if files_uploaded_counter:
            files_uploaded_counter.labels(
                file_type=file_ext,
                validation_status=OperationStatus.FAILED.value,
                batch_id=str(batch_id),
            ).inc()

        return {
            "file_name": file_name,
            "raw_file_storage_id": raw_file_storage_id,
            "status": ProcessingStatus.FAILED.value,
            "error_code": validation_error.error_detail.error_code,
            "error_message": validation_error.error_detail.message,
        }

    # Step 4: Store validated extracted plaintext and publish success event
    text_storage_id = await content_client.store_content(
        text.encode("utf-8"),
        ContentType.EXTRACTED_PLAINTEXT,
        main_correlation_id,
    )
    logger.info(
        f"Stored extracted plaintext for file {file_name}, text_storage_id: {text_storage_id}",
        extra={"correlation_id": str(main_correlation_id)},
    )

    # Calculate metadata for event
    content_md5_hash = hashlib.md5(file_content).hexdigest()
    file_size_bytes = len(file_content)

    # Construct success event WITH both storage IDs
    content_provisioned_event_data = EssayContentProvisionedV1(
        batch_id=batch_id,
        original_file_name=file_name,
        raw_file_storage_id=raw_file_storage_id,
        text_storage_id=text_storage_id,
        file_size_bytes=file_size_bytes,
        content_md5_hash=content_md5_hash,
        correlation_id=main_correlation_id,
        timestamp=datetime.now(UTC),
    )

    # Publish success event
    await event_publisher.publish_essay_content_provisioned(
        content_provisioned_event_data,
        main_correlation_id,
    )
    logger.info(
        f"Published EssayContentProvisionedV1 for file {file_name}",
        extra={"correlation_id": str(main_correlation_id)},
    )

    # Record metric for successful file processing
    file_ext = file_name.split(".")[-1].lower() if "." in file_name else "unknown"

    files_uploaded_counter = metrics.get("files_uploaded_total")
    if files_uploaded_counter:
        files_uploaded_counter.labels(
            file_type=file_ext,
            validation_status=OperationStatus.SUCCESS.value,
            batch_id=str(batch_id),
        ).inc()

    return {
        "file_name": file_name,
        "raw_file_storage_id": raw_file_storage_id,
        "text_storage_id": text_storage_id,
        "status": ProcessingStatus.COMPLETED.value,
    }
