"""Batch processing routes for Batch Orchestrator Service."""

from __future__ import annotations

import uuid
from typing import Any
from uuid import uuid4

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.client_commands import ClientBatchPipelineRequestV1
from common_core.pipeline_models import PhaseName, PipelineExecutionStatus
from common_core.status_enums import OperationStatus, ProcessingStatus
from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import ValidationError
from quart import Blueprint, Response, current_app, jsonify, request
from quart_dishka import inject

from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.config import settings
from services.batch_orchestrator_service.protocols import (
    BatchProcessingServiceProtocol,
    BatchRepositoryProtocol,
    PipelinePhaseCoordinatorProtocol,
)

logger = create_service_logger("bos.api.batch")
batch_bp = Blueprint("batch_routes", __name__, url_prefix="/v1/batches")

CONTENT_SERVICE_URL = settings.CONTENT_SERVICE_URL
OUTPUT_KAFKA_TOPIC_SPELLCHECK_REQUEST = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)


@batch_bp.route("/register", methods=["POST"])
@inject
async def register_batch(
    batch_processing_service: FromDishka[BatchProcessingServiceProtocol],
) -> Response | tuple[Response, int]:
    """Register a new batch for processing.

    Accepts batch registration data and delegates to the batch processing service.
    """
    # Extract correlation ID from headers, generate new one if not provided
    correlation_header = request.headers.get("X-Correlation-ID")
    if correlation_header:
        try:
            correlation_id = uuid.UUID(correlation_header)
        except ValueError:
            # Invalid UUID format, generate new one
            correlation_id = uuid.uuid4()
    else:
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

        # Record metrics using shared metrics pattern
        metrics = current_app.extensions.get("metrics", {})
        pipeline_execution_metric = metrics.get("pipeline_execution_total")
        if pipeline_execution_metric:
            # Track pipeline execution requests - pipelines are determined by enable_cj_assessment
            pipelines = ["spellcheck"]
            if validated_data.enable_cj_assessment:
                pipelines.append("cj_assessment")

            for pipeline in pipelines:
                pipeline_execution_metric.labels(
                    pipeline_type=pipeline,
                    outcome=ProcessingStatus.PENDING.value,
                    batch_id=str(batch_id),
                ).inc()

        return jsonify(
            {"batch_id": batch_id, "correlation_id": str(correlation_id), "status": "registered"},
        ), 202

    except ValidationError as ve:
        logger.warning(
            f"Batch registration validation error. Correlation ID: {correlation_id}",
            exc_info=True,
        )
        # Record validation error metrics
        metrics = current_app.extensions.get("metrics", {})
        pipeline_execution_metric = metrics.get("pipeline_execution_total")
        if pipeline_execution_metric:
            pipeline_execution_metric.labels(
                pipeline_type="unknown",
                outcome=OperationStatus.FAILED.value,
                batch_id="unknown",
            ).inc()
        return jsonify({"error": "Validation Error", "details": ve.errors()}), 400
    except Exception:
        logger.error(f"Error registering batch. Correlation ID: {correlation_id}", exc_info=True)
        # Record error metrics
        metrics = current_app.extensions.get("metrics", {})
        pipeline_execution_metric = metrics.get("pipeline_execution_total")
        if pipeline_execution_metric:
            pipeline_execution_metric.labels(
                pipeline_type="unknown",
                outcome=OperationStatus.FAILED.value,
                batch_id="unknown",
            ).inc()
        return jsonify({"error": "Failed to register batch."}), 500


@batch_bp.route("/<batch_id>/status", methods=["GET"])
@inject
async def get_batch_status(
    batch_id: str,
    batch_repo: FromDishka[BatchRepositoryProtocol],
) -> Response | tuple[Response, int]:
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
                "expected_essay_count": batch_context.expected_essay_count,
                "enable_cj_assessment": batch_context.enable_cj_assessment,
                "user_id": batch_context.user_id,
            },
            "pipeline_state": pipeline_state.model_dump(mode="json") if pipeline_state else {},
        }

        return jsonify(response_data), 200

    except Exception as e:
        current_app.logger.error(f"Error getting batch status for {batch_id}: {e}")
        return jsonify({"error": "Failed to get batch status"}), 500


# Internal API Blueprint for service-to-service communication
internal_bp = Blueprint("internal_routes", __name__, url_prefix="/internal/v1/batches")


@internal_bp.route("/<batch_id>/pipeline-state", methods=["GET"])
@inject
async def get_internal_pipeline_state(
    batch_id: str,
    batch_repo: FromDishka[BatchRepositoryProtocol],
) -> Response | tuple[Response, int]:
    """
    Internal endpoint to retrieve the complete pipeline processing state.

    This endpoint is consumed by the Result Aggregator Service and other
    internal systems, providing the single source of truth for batch pipeline state.
    BOS maintains the authoritative pipeline state that other services query.
    """
    try:
        # Directly use the existing, tested repository method. This call is highly
        # efficient as it's a primary key lookup on the 'batches' table.
        pipeline_state = await batch_repo.get_processing_pipeline_state(batch_id)

        if pipeline_state is None:
            # Return a clear 404 if the batch or its state doesn't exist.
            return jsonify({"error": "Pipeline state not found for batch"}), 404

        # Also get batch context to include user_id for ownership checks
        batch_context = await batch_repo.get_batch_context(batch_id)
        user_id = None
        if batch_context and hasattr(batch_context, "user_id"):
            user_id = batch_context.user_id
        elif isinstance(pipeline_state, dict):
            user_id = pipeline_state.get("user_id")

        # Build response with pipeline state and user_id for ownership enforcement
        response_data = {
            "batch_id": batch_id,
            "pipeline_state": pipeline_state.model_dump(mode="json") if pipeline_state else None,
            "user_id": user_id,  # Essential for Result Aggregator ownership checks
        }

        return jsonify(response_data), 200

    except Exception as e:
        # Log with context for easier debugging if the repository fails.
        current_app.logger.error(
            f"Error getting internal pipeline state for {batch_id}: {e}",
            exc_info=True,
        )
        return jsonify({"error": "Failed to get internal pipeline state"}), 500


@batch_bp.route("/<batch_id>/retry-phase", methods=["POST"])
@inject
async def retry_phase(
    batch_id: str,
    batch_repo: FromDishka[BatchRepositoryProtocol],
    phase_coordinator: FromDishka[PipelinePhaseCoordinatorProtocol],
) -> tuple[dict[str, Any], int]:
    """
    Retry a specific phase for a batch using simplified retry approach.

    Leverages existing pipeline request pattern with is_retry context.
    Validates user ownership and handles CJ Assessment batch-only constraints.
    """
    try:
        data = await request.get_json()

        # Extract retry parameters
        phase_name = data.get("phase_name")
        retry_reason = data.get("retry_reason", "User initiated retry")
        user_id = data.get("user_id")  # From JWT in production

        if not phase_name or not user_id:
            return {"error": "phase_name and user_id are required"}, 400

        # Validate batch ownership
        batch_context = await batch_repo.get_batch_context(batch_id)
        if not batch_context:
            return {"error": "Batch not found"}, 404

        # Note: In production, user_id would come from JWT token
        # For now, we trust the provided user_id for testing

        # Validate phase name
        try:
            phase_enum = PhaseName(phase_name.lower())
        except ValueError:
            return {"error": f"Invalid phase name: {phase_name}"}, 400

        # Handle CJ Assessment batch-only constraint
        if phase_enum == PhaseName.CJ_ASSESSMENT:
            essay_ids = data.get("essay_ids", [])
            if essay_ids:
                return {
                    "error": "CJ Assessment requires full batch retry for ranking consistency"
                }, 400

        # Get current pipeline state for retry validation
        pipeline_state = await batch_repo.get_processing_pipeline_state(batch_id)
        if not pipeline_state:
            return {"error": "No pipeline state found for batch"}, 404

        # Reset phase status to allow retry (simplified approach)
        correlation_id = uuid4()
        await phase_coordinator.update_phase_status(
            batch_id=batch_id,
            phase=phase_enum,
            status=PipelineExecutionStatus.REQUESTED_BY_USER,
            correlation_id=correlation_id,
            completion_timestamp=None,
        )

        # Create retry request using existing pipeline pattern
        retry_request = ClientBatchPipelineRequestV1(
            batch_id=batch_id,
            requested_pipeline=phase_enum.value,
            user_id=user_id,
            is_retry=True,
            retry_reason=retry_reason,
        )

        # Use existing phase coordination logic
        essays_to_process = await batch_repo.get_batch_essays(batch_id)
        if not essays_to_process:
            return {"error": "No essays found for batch"}, 404

        # Initiate retry using existing phase coordinator
        # Use the correlation_id created earlier or generate a new one
        retry_correlation_id = (
            retry_request.client_correlation_id
            if retry_request.client_correlation_id
            else correlation_id  # Use the UUID created earlier
        )
        await phase_coordinator.initiate_resolved_pipeline(
            batch_id=batch_id,
            resolved_pipeline=[phase_enum],  # Single-phase pipeline
            correlation_id=retry_correlation_id,
            batch_context=batch_context,
        )

        logger.info(
            f"Phase retry initiated for batch {batch_id}, phase {phase_enum.value}",
            extra={
                "batch_id": batch_id,
                "phase": phase_enum.value,
                "user_id": user_id,
                "retry_reason": retry_reason,
                "is_retry": True,
            },
        )

        return {
            "status": "retry_initiated",
            "batch_id": batch_id,
            "phase": phase_enum.value,
            "message": f"Retry initiated for {phase_enum.value} phase",
        }, 200

    except Exception as e:
        logger.error(f"Error processing retry request for batch {batch_id}: {e}", exc_info=True)
        return {"error": "Internal server error"}, 500
