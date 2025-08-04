"""Batch-related routes for Class Management Service."""

from __future__ import annotations

import uuid

from dishka import FromDishka
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, jsonify, request
from quart_dishka import inject

from services.class_management_service.metrics import CmsMetrics
from services.class_management_service.models_db import Student, UserClass
from services.class_management_service.protocols import ClassManagementServiceProtocol

logger = create_service_logger("class_management_service.api.batch")
batch_bp = Blueprint("batch_routes", __name__)


@batch_bp.route("/<batch_id>/student-associations", methods=["GET"])
@inject
async def get_batch_student_associations(
    batch_id: str,
    service: FromDishka[ClassManagementServiceProtocol[UserClass, Student]],
    metrics: FromDishka[CmsMetrics],
) -> Response | tuple[Response, int]:
    """Retrieve student-essay association suggestions for teacher validation."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401

    with metrics.http_request_duration_seconds.labels(
        method="GET", endpoint=f"/v1/batches/{batch_id}/student-associations"
    ).time():
        try:
            batch_uuid = uuid.UUID(batch_id)
            associations = await service.get_batch_student_associations(batch_uuid)
            
            metrics.http_requests_total.labels(
                method="GET", 
                endpoint=f"/v1/batches/{batch_id}/student-associations", 
                http_status=200
            ).inc()
            
            return jsonify({"associations": associations}), 200
            
        except ValueError:
            metrics.http_requests_total.labels(
                method="GET", 
                endpoint=f"/v1/batches/{batch_id}/student-associations", 
                http_status=400
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/batches/{batch_id}/student-associations", 
                error_type="bad_request"
            ).inc()
            return jsonify({"error": "Invalid batch ID format"}), 400
        except Exception as e:
            logger.error(f"Error retrieving batch student associations: {e}", exc_info=True)
            metrics.http_requests_total.labels(
                method="GET", 
                endpoint=f"/v1/batches/{batch_id}/student-associations", 
                http_status=500
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/batches/{batch_id}/student-associations", 
                error_type="server_error"
            ).inc()
            return jsonify({"error": "Internal server error"}), 500


@batch_bp.route("/<batch_id>/student-associations/confirm", methods=["POST"])
@inject
async def confirm_batch_student_associations(
    batch_id: str,
    service: FromDishka[ClassManagementServiceProtocol[UserClass, Student]],
    metrics: FromDishka[CmsMetrics],
) -> Response | tuple[Response, int]:
    """Confirm student-essay associations for a batch."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401

    # Get correlation ID from header or generate new one
    correlation_id_str = request.headers.get("X-Correlation-ID")
    if correlation_id_str:
        try:
            correlation_id = uuid.UUID(correlation_id_str)
        except ValueError:
            correlation_id = uuid.uuid4()
    else:
        correlation_id = uuid.uuid4()

    with metrics.http_request_duration_seconds.labels(
        method="POST", endpoint=f"/v1/batches/{batch_id}/student-associations/confirm"
    ).time():
        try:
            batch_uuid = uuid.UUID(batch_id)
            data = await request.get_json()
            
            # Process confirmations
            result = await service.confirm_batch_student_associations(
                batch_uuid, data, correlation_id
            )
            
            metrics.http_requests_total.labels(
                method="POST", 
                endpoint=f"/v1/batches/{batch_id}/student-associations/confirm", 
                http_status=200
            ).inc()
            
            return jsonify(result), 200
            
        except ValueError as e:
            logger.warning(f"Invalid request format: {e}")
            metrics.http_requests_total.labels(
                method="POST", 
                endpoint=f"/v1/batches/{batch_id}/student-associations/confirm", 
                http_status=400
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/batches/{batch_id}/student-associations/confirm", 
                error_type="bad_request"
            ).inc()
            return jsonify({"error": "Invalid batch ID format"}), 400
        except HuleEduError as e:
            logger.warning(
                f"Class management error during association confirmation: {e.error_detail.message}",
                extra={
                    "correlation_id": str(e.error_detail.correlation_id),
                    "error_code": e.error_detail.error_code,
                    "operation": e.error_detail.operation,
                },
            )
            metrics.http_requests_total.labels(
                method="POST", 
                endpoint=f"/v1/batches/{batch_id}/student-associations/confirm", 
                http_status=400
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/batches/{batch_id}/student-associations/confirm",
                error_type=str(e.error_detail.error_code).lower(),
            ).inc()
            return jsonify({"error": e.error_detail.model_dump()}), 400
        except Exception as e:
            logger.error(f"Error confirming batch student associations: {e}", exc_info=True)
            metrics.http_requests_total.labels(
                method="POST", 
                endpoint=f"/v1/batches/{batch_id}/student-associations/confirm", 
                http_status=500
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/batches/{batch_id}/student-associations/confirm", 
                error_type="server_error"
            ).inc()
            return jsonify({"error": "Internal server error"}), 500