"""
HuleEdu Content Service Application.

This module implements the Content Service REST API using Quart framework.
It provides endpoints for uploading and downloading content with proper
error handling, logging, and health checks. Content is stored as files
on the local filesystem with UUID-based identifiers.
"""

import uuid
from typing import Union

import aiofiles
import aiofiles.os  # Keep for await aiofiles.os.path.isfile
from config import settings
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from quart import Quart, Response, jsonify, request, send_file

# Configure structured logging for the service
configure_service_logging("content-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("api")

# Determine store root from settings
STORE_ROOT = settings.CONTENT_STORE_ROOT_PATH

app = Quart(__name__)


@app.before_serving
async def startup() -> None:
    try:
        STORE_ROOT.mkdir(
            parents=True, exist_ok=True
        )  # await aiofiles.os.makedirs is not needed for pathlib
        logger.info(f"Content store root initialized at: {STORE_ROOT.resolve()}")
    except Exception as e:
        logger.critical(
            f"Failed to create storage directory {STORE_ROOT.resolve()}: {e}",
            exc_info=True,
        )
        # Consider if the app should exit if this fails.


@app.post("/v1/content")
async def upload_content() -> Union[Response, tuple[Response, int]]:
    try:
        raw_data = await request.data
        if not raw_data:
            logger.warning("Upload attempt with no data.")
            return jsonify({"error": "No data provided in request body."}), 400

        content_id = uuid.uuid4().hex
        file_path = STORE_ROOT / content_id

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(raw_data)

        logger.info(f"Stored content with ID: {content_id} at {file_path.resolve()}")
        return jsonify({"storage_id": content_id}), 201
    except Exception as e:
        logger.error(f"Error during content upload: {e}", exc_info=True)
        return jsonify({"error": "Failed to store content."}), 500


@app.get("/v1/content/<string:content_id>")
async def download_content(content_id: str) -> Union[Response, tuple[Response, int]]:
    try:
        if not all(c in "0123456789abcdefABCDEF" for c in content_id) or len(content_id) != 32:
            logger.warning(f"Invalid content_id format received: {content_id}")
            return jsonify({"error": "Invalid content ID format."}), 400

        file_path = STORE_ROOT / content_id

        if not await aiofiles.os.path.isfile(str(file_path)):
            logger.warning(f"Content not found for ID: {content_id} at path {file_path.resolve()}")
            return jsonify({"error": "Content not found."}), 404

        logger.info(f"Serving content for ID: {content_id} from {file_path.resolve()}")
        return await send_file(file_path)
    except Exception as e:
        logger.error(f"Error during content download for ID {content_id}: {e}", exc_info=True)
        return jsonify({"error": "Failed to retrieve content."}), 500


@app.get("/healthz")
async def health_check() -> Union[Response, tuple[Response, int]]:
    # Basic check, can be expanded
    try:
        store_path = settings.CONTENT_STORE_ROOT_PATH
        path_exists = store_path.exists()
        path_is_dir = store_path.is_dir()
        if not path_exists or not path_is_dir:
            logger.error(f"Health check failed: Store root {STORE_ROOT.resolve()} not accessible.")
            return (
                jsonify({"status": "unhealthy", "message": "Storage not accessible"}),
                503,
            )
        return jsonify({"status": "ok", "message": "Content Service is healthy."}), 200
    except Exception as e:
        logger.error(f"Health check unexpected error: {e}", exc_info=True)
        return jsonify({"status": "unhealthy", "message": "Health check error"}), 500


# Hypercorn config for Quart services
# PDM scripts will use these to run the app
# Example: pdm run start (uses hypercorn_config.py)
# Example: pdm run dev (uses quart run --debug)

if __name__ == "__main__":
    # For local dev, not for production container
    # Port is now sourced from settings
    app.run(host="0.0.0.0", port=settings.PORT, debug=True)
