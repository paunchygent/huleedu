"""Content management routes for Content Service."""

import uuid
from pathlib import Path
from typing import Union

import aiofiles
import aiofiles.os  # Keep for await aiofiles.os.path.isfile
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import Counter
from quart import Blueprint, Response, jsonify, request, send_file

logger = create_service_logger("content.api.content")
content_bp = Blueprint('content_routes', __name__, url_prefix='/v1/content')

# Reference to store root and metrics (set by app.py)
STORE_ROOT: Path | None = None
CONTENT_OPERATIONS: Counter | None = None


def set_content_dependencies(store_root: Path, content_operations: Counter) -> None:
    """Set the store root and metrics references from app.py."""
    global STORE_ROOT, CONTENT_OPERATIONS
    STORE_ROOT = store_root
    CONTENT_OPERATIONS = content_operations


@content_bp.route("", methods=["POST"])
async def upload_content() -> Union[Response, tuple[Response, int]]:
    """Upload content endpoint."""
    if STORE_ROOT is None:
        logger.error("Store root not configured")
        return jsonify({"error": "Service configuration error."}), 500

    try:
        raw_data = await request.data
        if not raw_data:
            logger.warning("Upload attempt with no data.")
            if CONTENT_OPERATIONS:
                CONTENT_OPERATIONS.labels(operation='upload', status='failed').inc()
            return jsonify({"error": "No data provided in request body."}), 400

        content_id = uuid.uuid4().hex
        file_path = STORE_ROOT / content_id

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(raw_data)

        logger.info(f"Stored content with ID: {content_id} at {file_path.resolve()}")
        if CONTENT_OPERATIONS:
            CONTENT_OPERATIONS.labels(operation='upload', status='success').inc()
        return jsonify({"storage_id": content_id}), 201
    except Exception as e:
        logger.error(f"Error during content upload: {e}", exc_info=True)
        if CONTENT_OPERATIONS:
            CONTENT_OPERATIONS.labels(operation='upload', status='error').inc()
        return jsonify({"error": "Failed to store content."}), 500


@content_bp.route("/<string:content_id>", methods=["GET"])
async def download_content(content_id: str) -> Union[Response, tuple[Response, int]]:
    """Download content endpoint."""
    if STORE_ROOT is None:
        logger.error("Store root not configured")
        return jsonify({"error": "Service configuration error."}), 500

    try:
        if not all(c in "0123456789abcdefABCDEF" for c in content_id) or len(content_id) != 32:
            logger.warning(f"Invalid content_id format received: {content_id}")
            if CONTENT_OPERATIONS:
                CONTENT_OPERATIONS.labels(operation='download', status='failed').inc()
            return jsonify({"error": "Invalid content ID format."}), 400

        file_path = STORE_ROOT / content_id

        if not await aiofiles.os.path.isfile(str(file_path)):
            logger.warning(f"Content not found for ID: {content_id} at path {file_path.resolve()}")
            if CONTENT_OPERATIONS:
                CONTENT_OPERATIONS.labels(operation='download', status='not_found').inc()
            return jsonify({"error": "Content not found."}), 404

        logger.info(f"Serving content for ID: {content_id} from {file_path.resolve()}")
        if CONTENT_OPERATIONS:
            CONTENT_OPERATIONS.labels(operation='download', status='success').inc()
        return await send_file(file_path)
    except Exception as e:
        logger.error(f"Error during content download for ID {content_id}: {e}", exc_info=True)
        if CONTENT_OPERATIONS:
            CONTENT_OPERATIONS.labels(operation='download', status='error').inc()
        return jsonify({"error": "Failed to retrieve content."}), 500
