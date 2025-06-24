"""Content management routes for Content Service."""

from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, jsonify, request, send_file
from quart_dishka import inject

from common_core.observability_enums import OperationType
from common_core.status_enums import OperationStatus
from services.content_service.protocols import ContentMetricsProtocol, ContentStoreProtocol

logger = create_service_logger("content.api.content")
content_bp = Blueprint("content_routes", __name__, url_prefix="/v1/content")


@content_bp.route("", methods=["POST"])
@inject
async def upload_content(
    store: FromDishka[ContentStoreProtocol],
    metrics: FromDishka[ContentMetricsProtocol],
) -> Response | tuple[Response, int]:
    """Upload content endpoint."""
    try:
        raw_data = await request.data
        if not raw_data:
            logger.warning("Upload attempt with no data.")
            metrics.record_operation(OperationType.UPLOAD, OperationStatus.FAILED)
            return jsonify({"error": "No data provided in request body."}), 400

        content_id = await store.save_content(raw_data)
        metrics.record_operation(OperationType.UPLOAD, OperationStatus.SUCCESS)
        return jsonify({"storage_id": content_id}), 201
    except Exception as e:
        logger.error(f"Error during content upload: {e}", exc_info=True)
        metrics.record_operation(OperationType.UPLOAD, OperationStatus.ERROR)
        return jsonify({"error": "Failed to store content."}), 500


@content_bp.route("/<string:content_id>", methods=["GET"])
@inject
async def download_content(
    content_id: str,
    store: FromDishka[ContentStoreProtocol],
    metrics: FromDishka[ContentMetricsProtocol],
) -> Response | tuple[Response, int]:
    """Download content endpoint."""
    try:
        if not all(c in "0123456789abcdefABCDEF" for c in content_id) or len(content_id) != 32:
            logger.warning(f"Invalid content_id format received: {content_id}")
            metrics.record_operation(OperationType.DOWNLOAD, OperationStatus.FAILED)
            return jsonify({"error": "Invalid content ID format."}), 400

        if not await store.content_exists(content_id):
            logger.warning(f"Content not found for ID: {content_id}")
            metrics.record_operation(OperationType.DOWNLOAD, OperationStatus.NOT_FOUND)
            return jsonify({"error": "Content not found."}), 404

        file_path = await store.get_content_path(content_id)
        logger.info(f"Serving content for ID: {content_id} from {file_path.resolve()}")
        metrics.record_operation(OperationType.DOWNLOAD, OperationStatus.SUCCESS)
        return await send_file(file_path)
    except Exception as e:
        logger.error(f"Error during content download for ID {content_id}: {e}", exc_info=True)
        metrics.record_operation(OperationType.DOWNLOAD, OperationStatus.ERROR)
        return jsonify({"error": "Failed to retrieve content."}), 500
