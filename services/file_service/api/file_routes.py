"""File upload and processing routes for File Service."""

from __future__ import annotations

import asyncio
import uuid
from typing import Union

from core_logic import process_single_file_upload
from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from protocols import (
    ContentServiceClientProtocol,
    EventPublisherProtocol,
    TextExtractorProtocol,
)
from quart import Blueprint, Response, jsonify, request
from quart_dishka import inject

logger = create_service_logger("file_service.api.file_routes")
file_bp = Blueprint('file_routes', __name__, url_prefix='/v1/files')


@file_bp.route("/batch", methods=["POST"])
@inject
async def upload_batch_files(
    text_extractor: FromDishka[TextExtractorProtocol],
    content_client: FromDishka[ContentServiceClientProtocol],
    event_publisher: FromDishka[EventPublisherProtocol]
) -> Union[Response, tuple[Response, int]]:
    """
    Handle batch file upload endpoint.

    Accepts multiple files associated with a batch_id and processes them
    concurrently to extract text, store content, and publish readiness events.
    """
    try:
        form_data = await request.form
        batch_id = form_data.get("batch_id")
        files = await request.files

        if not batch_id:
            logger.warning("Batch upload attempt without batch_id.")
            return jsonify({"error": "batch_id is required in form data."}), 400

        uploaded_files = files.getlist('files')  # Assuming form field name is 'files'
        if not uploaded_files:
            logger.warning(f"No files provided for batch {batch_id}.")
            return jsonify({"error": "No files provided in 'files' field."}), 400

        main_correlation_id = uuid.uuid4()
        logger.info(
            f"Received {len(uploaded_files)} files for batch {batch_id}. "
            f"Correlation ID: {main_correlation_id}"
        )

        tasks = []
        for file_storage in uploaded_files:
            if file_storage and file_storage.filename:
                file_content = file_storage.read()
                # Pass all required injected dependencies to process_single_file_upload
                task = asyncio.create_task(
                    process_single_file_upload(
                        batch_id=batch_id,
                        file_content=file_content,
                        file_name=file_storage.filename,
                        main_correlation_id=main_correlation_id,
                        text_extractor=text_extractor,
                        content_client=content_client,
                        event_publisher=event_publisher
                    )
                )
                tasks.append(task)

        # Handle task exceptions with done callback
        def _handle_task_result(task: asyncio.Task) -> None:
            if task.exception():
                logger.error(
                    f"Error processing uploaded file: {task.exception()}",
                    exc_info=task.exception()
                )

        for task in tasks:
            task.add_done_callback(_handle_task_result)

        return jsonify({
            "message": (
                f"{len(uploaded_files)} files received for batch {batch_id} "
                "and are being processed."
            ),
            "batch_id": batch_id,
            "correlation_id": str(main_correlation_id)
        }), 202

    except Exception as e:
        logger.error(f"Error in batch file upload endpoint: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
