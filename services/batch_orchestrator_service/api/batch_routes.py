"""Batch processing routes for Batch Orchestrator Service."""

from __future__ import annotations

import uuid
from typing import Optional, Union

from api_models import BatchRegistrationRequestV1
from config import settings
from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import Counter
from protocols import (
    BatchProcessingServiceProtocol,
    BatchRepositoryProtocol,
)
from pydantic import ValidationError
from quart import Blueprint, Response, current_app, jsonify, request
from quart_dishka import inject

from common_core.enums import ProcessingEvent, topic_name

logger = create_service_logger("bos.api.batch")
batch_bp = Blueprint("batch_routes", __name__, url_prefix="/v1/batches")

CONTENT_SERVICE_URL = settings.CONTENT_SERVICE_URL
OUTPUT_KAFKA_TOPIC_SPELLCHECK_REQUEST = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)

# Global metrics reference (initialized in app.py)
BATCH_OPERATIONS: Optional[Counter] = None


def set_batch_operations_metric(metric: Counter) -> None:
    """Set the batch operations metric reference."""
    global BATCH_OPERATIONS
    BATCH_OPERATIONS = metric


@batch_bp.route("/register", methods=["POST"])
@inject
async def register_batch(
    batch_processing_service: FromDishka[BatchProcessingServiceProtocol],
) -> Union[Response, tuple[Response, int]]:
    """Register a new batch for processing.

    Accepts batch registration data and delegates to the batch processing service.
    """
    correlation_id = uuid.uuid4()
    try:
        raw_request_data = await request.get_json()
        if not raw_request_data:
            return jsonify({"error": "Request body must be valid JSON"}), 400

        validated_data = BatchRegistrationRequestV1(**raw_request_data)

        # Delegate business logic to service layer
        batch_id = await batch_processing_service.register_new_batch(validated_data, correlation_id)

        logger.info(
            f"Batch {batch_id} registered successfully via service layer",
            extra={"correlation_id": str(correlation_id)},
        )

        # Record metrics
        if BATCH_OPERATIONS:
            BATCH_OPERATIONS.labels(operation="register_batch", status="success").inc()

        return jsonify(
            {"batch_id": batch_id, "correlation_id": str(correlation_id), "status": "registered"}
        ), 202

    except ValidationError as ve:
        logger.warning(
            f"Batch registration validation error. Correlation ID: {correlation_id}", exc_info=True
        )
        if BATCH_OPERATIONS:
            BATCH_OPERATIONS.labels(operation="register_batch", status="validation_error").inc()
        return jsonify({"error": "Validation Error", "details": ve.errors()}), 400
    except Exception:
        logger.error(f"Error registering batch. Correlation ID: {correlation_id}", exc_info=True)
        if BATCH_OPERATIONS:
            BATCH_OPERATIONS.labels(operation="register_batch", status="error").inc()
        return jsonify({"error": "Failed to register batch."}), 500


@batch_bp.route("/v1/batches/<batch_id>/status", methods=["GET"])
@inject
async def get_batch_status(
    batch_id: str,
    batch_repo: BatchRepositoryProtocol,
) -> Union[Response, tuple[Response, int]]:
    """Get the current status and pipeline state of a batch."""
    try:
        # Get batch context and pipeline state
        batch_context = await batch_repo.get_batch_context(batch_id)
        pipeline_state = await batch_repo.get_processing_pipeline_state(batch_id)

        if not batch_context:
            return jsonify({"error": "Batch not found"}), 404

        # Build response with batch info and pipeline status
        response_data = {
            "batch_id": batch_id,
            "batch_context": {
                "course_code": batch_context.course_code,
                "class_designation": batch_context.class_designation,
                "expected_essay_count": batch_context.expected_essay_count,
                "enable_cj_assessment": batch_context.enable_cj_assessment,
            },
            "pipeline_state": pipeline_state or {},
        }

        return jsonify(response_data), 200

    except Exception as e:
        current_app.logger.error(f"Error getting batch status for {batch_id}: {e}")
        return jsonify({"error": "Failed to get batch status"}), 500

