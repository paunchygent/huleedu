"""File upload and processing routes for File Service."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from common_core.events.file_management_events import BatchFileAddedV1, BatchFileRemovedV1
from dishka import FromDishka
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, jsonify, request
from quart_dishka import inject

from services.file_service.core_logic import process_single_file_upload
from services.file_service.protocols import (
    BatchStateValidatorProtocol,
    ContentServiceClientProtocol,
    ContentValidatorProtocol,
    EventPublisherProtocol,
    TextExtractorProtocol,
)

logger = create_service_logger("file_service.api.file_routes")
file_bp = Blueprint("file_routes", __name__, url_prefix="/v1/files")


@file_bp.route("/batch", methods=["POST"])
@inject
async def upload_batch_files(
    text_extractor: FromDishka[TextExtractorProtocol],
    content_validator: FromDishka[ContentValidatorProtocol],
    content_client: FromDishka[ContentServiceClientProtocol],
    event_publisher: FromDishka[EventPublisherProtocol],
    batch_validator: FromDishka[BatchStateValidatorProtocol],
    metrics: FromDishka[dict[str, Any]],
) -> Response | tuple[Response, int]:
    """
    Handle batch file upload endpoint with state validation.

    Accepts multiple files associated with a batch_id and processes them
    concurrently to extract text, validate content, store content, and publish events.
    Validates that the batch can be modified before processing any files.
    """
    try:
        form_data = await request.form
        batch_id = form_data.get("batch_id")
        files = await request.files

        if not batch_id:
            logger.warning("Batch upload attempt without batch_id.")
            return jsonify({"error": "batch_id is required in form data."}), 400

        # Get user_id from authenticated request (provided by API Gateway)
        user_id = request.headers.get("X-User-ID")
        if not user_id:
            logger.warning(f"Batch upload attempt for {batch_id} without user authentication.")
            return jsonify({"error": "User authentication required"}), 401

        # Generate correlation ID first for all operations
        correlation_id_header = request.headers.get("X-Correlation-ID")
        if correlation_id_header:
            try:
                main_correlation_id = uuid.UUID(correlation_id_header)
                logger.info(f"Using correlation ID from header: {main_correlation_id}")
            except ValueError:
                logger.warning(
                    f"Invalid correlation ID format in header: {correlation_id_header}, "
                    "generating new one",
                )
                main_correlation_id = uuid.uuid4()
        else:
            main_correlation_id = uuid.uuid4()

        # Validate batch can be modified before processing any files
        try:
            await batch_validator.can_modify_batch_files(batch_id, user_id, main_correlation_id)
        except HuleEduError as e:
            logger.info(
                f"File upload blocked for batch {batch_id} by user {user_id}: "
                f"{e.error_detail.message}"
            )
            return jsonify({"error": e.error_detail.model_dump()}), 409

        uploaded_files = files.getlist("files")  # Assuming form field name is 'files'
        if not uploaded_files:
            logger.warning(f"No files provided for batch {batch_id}.")
            return jsonify({"error": "No files provided in 'files' field."}), 400

        logger.info(
            f"Received {len(uploaded_files)} files for batch {batch_id} from user {user_id}. "
            f"Correlation ID: {main_correlation_id}",
        )

        tasks = []
        for file_storage in uploaded_files:
            if file_storage and file_storage.filename:
                file_content = file_storage.read()
                file_upload_id = str(uuid.uuid4())  # Generate unique tracking ID
                # Pass all required injected dependencies to process_single_file_upload
                task = asyncio.create_task(
                    process_single_file_upload(
                        batch_id=batch_id,
                        file_upload_id=file_upload_id,
                        file_content=file_content,
                        file_name=file_storage.filename,
                        main_correlation_id=main_correlation_id,
                        text_extractor=text_extractor,
                        content_validator=content_validator,
                        content_client=content_client,
                        event_publisher=event_publisher,
                        metrics=metrics,
                    ),
                )
                tasks.append(task)

        # Handle task exceptions with done callback
        def _handle_task_result(task: asyncio.Task) -> None:
            if task.exception():
                logger.error(
                    f"Error processing uploaded file: {task.exception()}",
                    exc_info=task.exception(),
                )

        for task in tasks:
            task.add_done_callback(_handle_task_result)

        return jsonify(
            {
                "message": (
                    f"{len(uploaded_files)} files received for batch {batch_id} "
                    "and are being processed."
                ),
                "batch_id": batch_id,
                "correlation_id": str(main_correlation_id),
            },
        ), 202

    except Exception as e:
        logger.error(f"Error in batch file upload endpoint: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@file_bp.route("/batch/<batch_id>/state", methods=["GET"])
@inject
async def get_batch_state(
    batch_id: str,
    batch_validator: FromDishka[BatchStateValidatorProtocol],
) -> Response | tuple[Response, int]:
    """
    Get the lock status of a batch.

    Returns detailed information about whether the batch can be modified
    and the current pipeline state.
    """
    try:
        # Get user_id from authenticated request (provided by API Gateway)
        user_id = request.headers.get("X-User-ID")
        if not user_id:
            logger.warning(f"Batch state query for {batch_id} without user authentication.")
            return jsonify({"error": "User authentication required"}), 401

        # Generate correlation ID for this operation
        correlation_id_header = request.headers.get("X-Correlation-ID")
        if correlation_id_header:
            try:
                correlation_id = uuid.UUID(correlation_id_header)
            except ValueError:
                correlation_id = uuid.uuid4()
        else:
            correlation_id = uuid.uuid4()

        # Get detailed batch lock status
        lock_status = await batch_validator.get_batch_lock_status(batch_id, correlation_id)

        logger.info(f"Batch state query for {batch_id} by user {user_id}")

        return jsonify({"batch_id": batch_id, "lock_status": lock_status}), 200

    except Exception as e:
        logger.error(f"Error getting batch state for {batch_id}: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@file_bp.route("/batch/<batch_id>/files", methods=["POST"])
@inject
async def add_files_to_batch(
    batch_id: str,
    text_extractor: FromDishka[TextExtractorProtocol],
    content_validator: FromDishka[ContentValidatorProtocol],
    content_client: FromDishka[ContentServiceClientProtocol],
    event_publisher: FromDishka[EventPublisherProtocol],
    batch_validator: FromDishka[BatchStateValidatorProtocol],
    metrics: FromDishka[dict[str, Any]],
) -> Response | tuple[Response, int]:
    """
    Add new files to an existing batch.

    Similar to the original batch upload but for adding files to an existing batch.
    Validates that the batch can be modified before processing any files.
    """
    try:
        files = await request.files

        # Get user_id from authenticated request (provided by API Gateway)
        user_id = request.headers.get("X-User-ID")
        if not user_id:
            logger.warning(
                f"File addition attempt for batch {batch_id} without user authentication."
            )
            return jsonify({"error": "User authentication required"}), 401

        # Generate correlation ID first for all operations
        correlation_id_header = request.headers.get("X-Correlation-ID")
        if correlation_id_header:
            try:
                main_correlation_id = uuid.UUID(correlation_id_header)
                logger.info(f"Using correlation ID from header: {main_correlation_id}")
            except ValueError:
                logger.warning(
                    f"Invalid correlation ID format in header: {correlation_id_header}, "
                    "generating new one",
                )
                main_correlation_id = uuid.uuid4()
        else:
            main_correlation_id = uuid.uuid4()

        # Validate batch can be modified before processing any files
        try:
            await batch_validator.can_modify_batch_files(batch_id, user_id, main_correlation_id)
        except HuleEduError as e:
            logger.info(
                f"File addition blocked for batch {batch_id} by user {user_id}: "
                f"{e.error_detail.message}"
            )
            return jsonify({"error": e.error_detail.model_dump()}), 409

        uploaded_files = files.getlist("files")  # Assuming form field name is 'files'
        if not uploaded_files:
            logger.warning(f"No files provided for batch {batch_id}.")
            return jsonify({"error": "No files provided in 'files' field."}), 400

        logger.info(
            f"Adding {len(uploaded_files)} files to existing batch {batch_id} by user {user_id}. "
            f"Correlation ID: {main_correlation_id}",
        )

        tasks = []
        added_files = []

        for file_storage in uploaded_files:
            if file_storage and file_storage.filename:
                file_content = file_storage.read()
                file_upload_id = str(uuid.uuid4())  # Generate tracking ID for each file

                # Track file for event publishing
                added_files.append(
                    {"file_upload_id": file_upload_id, "filename": file_storage.filename}
                )

                # Pass all required injected dependencies to process_single_file_upload
                task = asyncio.create_task(
                    process_single_file_upload(
                        batch_id=batch_id,
                        file_upload_id=file_upload_id,
                        file_content=file_content,
                        file_name=file_storage.filename,
                        main_correlation_id=main_correlation_id,
                        text_extractor=text_extractor,
                        content_validator=content_validator,
                        content_client=content_client,
                        event_publisher=event_publisher,
                        metrics=metrics,
                    ),
                )
                tasks.append(task)

        # Handle task exceptions with done callback
        def _handle_task_result(task: asyncio.Task) -> None:
            if task.exception():
                logger.error(
                    f"Error processing uploaded file: {task.exception()}",
                    exc_info=task.exception(),
                )

        for task in tasks:
            task.add_done_callback(_handle_task_result)

        # Publish BatchFileAddedV1 events for successfully queued files
        for file_info in added_files:
            try:
                event_data = BatchFileAddedV1(
                    batch_id=batch_id,
                    file_upload_id=file_info["file_upload_id"],
                    filename=file_info["filename"],
                    user_id=user_id,
                )
                await event_publisher.publish_batch_file_added_v1(event_data, main_correlation_id)
            except Exception as e:
                logger.error(f"Error publishing BatchFileAddedV1 event: {e}", exc_info=True)

        return jsonify(
            {
                "message": (
                    f"{len(uploaded_files)} files added to batch {batch_id} "
                    "and are being processed."
                ),
                "batch_id": batch_id,
                "correlation_id": str(main_correlation_id),
                "added_files": len(added_files),
            },
        ), 202

    except Exception as e:
        logger.error(f"Error adding files to batch {batch_id}: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@file_bp.route("/batch/<batch_id>/files/<file_upload_id>", methods=["DELETE"])
@inject
async def remove_file_from_batch(
    batch_id: str,
    file_upload_id: str,
    batch_validator: FromDishka[BatchStateValidatorProtocol],
    event_publisher: FromDishka[EventPublisherProtocol],
) -> Response | tuple[Response, int]:
    """
    Remove a file from an existing batch.

    Validates that the batch can be modified and publishes a BatchFileRemovedV1 event.
    The actual file removal coordination is handled by downstream services.
    """
    try:
        # Get user_id from authenticated request (provided by API Gateway)
        user_id = request.headers.get("X-User-ID")
        if not user_id:
            warning_msg = (
                "File removal attempt for batch %s, file %s without user authentication."
                % (batch_id, file_upload_id)
            )
            logger.warning(warning_msg)
            return jsonify({"error": "User authentication required"}), 401

        # Check for X-Correlation-ID header for distributed tracing
        correlation_id_header = request.headers.get("X-Correlation-ID")
        if correlation_id_header:
            try:
                correlation_id = uuid.UUID(correlation_id_header)
                logger.info(f"Using correlation ID from header: {correlation_id}")
            except ValueError:
                logger.warning(
                    f"Invalid correlation ID format in header: {correlation_id_header}, "
                    "generating new one",
                )
                correlation_id = uuid.uuid4()
        else:
            correlation_id = uuid.uuid4()

        # Validate batch can be modified before removing files
        try:
            await batch_validator.can_modify_batch_files(batch_id, user_id, correlation_id)
        except HuleEduError as e:
            info_msg = "File removal blocked for batch %s, file %s by user %s: %s" % (
                batch_id,
                file_upload_id,
                user_id,
                e.error_detail.message,
            )
            logger.info(info_msg)
            return jsonify({"error": e.error_detail.model_dump()}), 409

        logger.info(
            f"Removing file {file_upload_id} from batch {batch_id} by user {user_id}. "
            f"Correlation ID: {correlation_id}",
        )

        # Publish BatchFileRemovedV1 event
        # Note: We don't have the original filename, so we'll use file_upload_id as placeholder
        # In a real implementation, this would require querying the file metadata
        event_data = BatchFileRemovedV1(
            batch_id=batch_id,
            file_upload_id=file_upload_id,
            # Placeholder - would be actual filename in production
            filename=f"file_{file_upload_id}",
            user_id=user_id,
        )

        await event_publisher.publish_batch_file_removed_v1(event_data, correlation_id)

        return jsonify(
            {
                "message": (
                    f"File removal request processed for file {file_upload_id} in batch {batch_id}"
                ),
                "batch_id": batch_id,
                "file_upload_id": file_upload_id,
                "correlation_id": str(correlation_id),
            }
        ), 200

    except Exception as e:
        logger.error(
            f"Error removing file {file_upload_id} from batch {batch_id}: {e}", exc_info=True
        )
        return jsonify({"error": "Internal server error"}), 500
