"""Content management routes for Content Service."""

from __future__ import annotations

import uuid
from pathlib import Path

import aiofiles
from common_core.observability_enums import OperationType
from common_core.status_enums import OperationStatus
from dishka import FromDishka
from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_content_service_error,
    raise_validation_error,
)
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, jsonify, request
from quart_dishka import inject

from services.content_service.protocols import (
    ContentMetricsProtocol,
    ContentRepositoryProtocol,
    ContentStoreProtocol,
)

logger = create_service_logger("content.api.content")
content_bp = Blueprint("content_routes", __name__, url_prefix="/v1/content")


@content_bp.route("", methods=["POST"])
@inject
async def upload_content(
    repository: FromDishka[ContentRepositoryProtocol],
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

        # Determine content type from request, defaulting to text/plain for backward compatibility
        content_type = request.headers.get("Content-Type") or "text/plain"

        content_id = uuid.uuid4().hex
        await repository.save_content(content_id, raw_data, content_type, correlation_id)
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
    repository: FromDishka[ContentRepositoryProtocol],
    legacy_store: FromDishka[ContentStoreProtocol],
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

        content_bytes, content_type = await _get_content_with_legacy_fallback(
            content_id,
            repository,
            legacy_store,
            correlation_id,
        )
        logger.info(
            "Serving content for ID: %s", content_id, extra={"correlation_id": str(correlation_id)}
        )
        metrics.record_operation(OperationType.DOWNLOAD, OperationStatus.SUCCESS)
        return _build_download_response(content_bytes, content_type)
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


LEGACY_FALLBACK_CONTENT_TYPE = "application/octet-stream"


async def _get_content_with_legacy_fallback(
    content_id: str,
    repository: ContentRepositoryProtocol,
    legacy_store: ContentStoreProtocol,
    correlation_id: uuid.UUID,
) -> tuple[bytes, str]:
    """Fetch content from the DB and fall back to the filesystem if needed."""

    try:
        return await repository.get_content(content_id, correlation_id)
    except HuleEduError as exc:
        if exc.error_detail.error_code != "RESOURCE_NOT_FOUND":
            raise

        legacy_payload = await _load_legacy_content_from_store(
            content_id,
            legacy_store,
            correlation_id,
        )
        if legacy_payload is None:
            raise

        content_bytes, content_type = legacy_payload
        await _backfill_legacy_content(
            repository,
            content_id,
            content_bytes,
            content_type,
            correlation_id,
        )
        return content_bytes, content_type


async def _load_legacy_content_from_store(
    content_id: str,
    legacy_store: ContentStoreProtocol,
    correlation_id: uuid.UUID,
) -> tuple[bytes, str] | None:
    """Return legacy filesystem content if present."""

    try:
        file_path = await legacy_store.get_content_path(content_id, correlation_id)
    except HuleEduError as legacy_error:
        if legacy_error.error_detail.error_code == "RESOURCE_NOT_FOUND":
            logger.info(
                "Legacy content not found for ID: %s",
                content_id,
                extra={"correlation_id": str(correlation_id)},
            )
            return None
        raise

    try:
        async with aiofiles.open(file_path, "rb") as legacy_file:
            legacy_bytes = await legacy_file.read()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(
            "Failed to read legacy content for ID %s from %s: %s",
            content_id,
            Path(file_path).resolve(),
            exc,
            extra={"correlation_id": str(correlation_id)},
            exc_info=True,
        )
        raise_content_service_error(
            service="content_service",
            operation="load_legacy_content",
            message=f"Failed to read legacy content: {exc}",
            correlation_id=correlation_id,
            content_id=content_id,
        )

    logger.info(
        "Loaded legacy filesystem content for ID: %s",
        content_id,
        extra={"correlation_id": str(correlation_id)},
    )
    return legacy_bytes, LEGACY_FALLBACK_CONTENT_TYPE


async def _backfill_legacy_content(
    repository: ContentRepositoryProtocol,
    content_id: str,
    content_bytes: bytes,
    content_type: str,
    correlation_id: uuid.UUID,
) -> None:
    """Persist legacy payloads into the new table for seamless migration."""

    try:
        await repository.save_content(content_id, content_bytes, content_type, correlation_id)
        logger.info(
            "Backfilled legacy content for ID: %s",
            content_id,
            extra={"correlation_id": str(correlation_id)},
        )
    except Exception as exc:  # pragma: no cover - best-effort backfill
        logger.warning(
            "Failed to backfill legacy content for ID %s: %s",
            content_id,
            exc,
            extra={"correlation_id": str(correlation_id)},
        )


def _build_download_response(content_bytes: bytes, content_type: str | None) -> Response:
    """Create the Quart response, preserving any Content-Type parameters."""

    resolved_content_type = content_type or "application/octet-stream"
    return Response(response=content_bytes, content_type=resolved_content_type)
