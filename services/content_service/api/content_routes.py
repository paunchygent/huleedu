"""Content management routes for Content Service."""

from __future__ import annotations

import uuid

from common_core.observability_enums import OperationType
from common_core.status_enums import OperationStatus
from dishka import FromDishka
from huleedu_service_libs.error_handling import HuleEduError, raise_validation_error
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, jsonify, request, send_file
from quart_dishka import inject

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
    correlation_id = uuid.uuid4()

    try:
        raw_data = await request.data
        if not raw_data:
            logger.warning(
                "Upload attempt with no data.",
                extra={"correlation_id": str(correlation_id)},
            )
            metrics.record_operation(OperationType.UPLOAD, OperationStatus.FAILED)
            raise_validation_error(
                service="content_service",
                operation="upload_content",
                field="request_body",
                message="No data provided in request body",
                correlation_id=correlation_id,
            )

        content_id = await store.save_content(raw_data, correlation_id)
        metrics.record_operation(OperationType.UPLOAD, OperationStatus.SUCCESS)
        return jsonify({"storage_id": content_id, "correlation_id": str(correlation_id)}), 201
    except HuleEduError as e:
        logger.warning(
            f"Content upload failed: {e.error_detail.message}",
            extra={
                "correlation_id": str(e.error_detail.correlation_id),
                "error_code": e.error_detail.error_code,
            },
        )
        metrics.record_operation(OperationType.UPLOAD, OperationStatus.FAILED)
        return jsonify({"error": e.error_detail.model_dump()}), 400
    except Exception as e:
        logger.error(
            f"Unexpected error during content upload: {e}",
            extra={"correlation_id": str(correlation_id)},
            exc_info=True,
        )
        metrics.record_operation(OperationType.UPLOAD, OperationStatus.ERROR)
        return jsonify(
            {
                "error": {
                    "error_code": "UNKNOWN_ERROR",
                    "message": "An unexpected error occurred during upload",
                    "correlation_id": str(correlation_id),
                }
            }
        ), 500


@content_bp.route("/<string:content_id>", methods=["GET"])
@inject
async def download_content(
    content_id: str,
    store: FromDishka[ContentStoreProtocol],
    metrics: FromDishka[ContentMetricsProtocol],
) -> Response | tuple[Response, int]:
    """Download content endpoint."""
    correlation_id = uuid.uuid4()

    try:
        if not all(c in "0123456789abcdefABCDEF" for c in content_id) or len(content_id) != 32:
            logger.warning(
                f"Invalid content_id format received: {content_id}",
                extra={"correlation_id": str(correlation_id)},
            )
            metrics.record_operation(OperationType.DOWNLOAD, OperationStatus.FAILED)
            raise_validation_error(
                service="content_service",
                operation="download_content",
                field="content_id",
                message="Invalid content ID format - must be 32 character hex string",
                correlation_id=correlation_id,
                value=content_id,
            )

        file_path = await store.get_content_path(content_id, correlation_id)
        logger.info(
            f"Serving content for ID: {content_id} from {file_path.resolve()}",
            extra={"correlation_id": str(correlation_id)},
        )
        metrics.record_operation(OperationType.DOWNLOAD, OperationStatus.SUCCESS)
        return await send_file(file_path)
    except HuleEduError as e:
        logger.warning(
            f"Content download failed: {e.error_detail.message}",
            extra={
                "correlation_id": str(e.error_detail.correlation_id),
                "error_code": e.error_detail.error_code,
                "content_id": content_id,
            },
        )
        if e.error_detail.error_code == "RESOURCE_NOT_FOUND":
            metrics.record_operation(OperationType.DOWNLOAD, OperationStatus.NOT_FOUND)
            return jsonify({"error": e.error_detail.model_dump()}), 404
        else:
            metrics.record_operation(OperationType.DOWNLOAD, OperationStatus.FAILED)
            return jsonify({"error": e.error_detail.model_dump()}), 400
    except Exception as e:
        logger.error(
            f"Unexpected error during content download for ID {content_id}: {e}",
            extra={"correlation_id": str(correlation_id)},
            exc_info=True,
        )
        metrics.record_operation(OperationType.DOWNLOAD, OperationStatus.ERROR)
        return jsonify(
            {
                "error": {
                    "error_code": "UNKNOWN_ERROR",
                    "message": "An unexpected error occurred during download",
                    "correlation_id": str(correlation_id),
                    "content_id": content_id,
                }
            }
        ), 500
