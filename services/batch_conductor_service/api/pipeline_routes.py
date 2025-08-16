"""Pipeline resolution routes for Batch Conductor Service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dishka import FromDishka
from pydantic import ValidationError
from quart import Blueprint, Response, jsonify, request
from quart_dishka import inject

from huleedu_service_libs.logging_utils import create_service_logger
from services.batch_conductor_service.api_models import (
    BCSPipelineDefinitionRequestV1,
)
from services.batch_conductor_service.protocols import (
    BatchStateRepositoryProtocol,
    DlqProducerProtocol,
    PipelineResolutionServiceProtocol,
)

if TYPE_CHECKING:
    pass

logger = create_service_logger("bcs.api.pipeline")
pipeline_bp = Blueprint("pipeline_routes", __name__)


@pipeline_bp.route("/internal/v1/pipelines/define", methods=["POST"])
@inject
async def define_pipeline(
    pipeline_service: FromDishka[PipelineResolutionServiceProtocol],
    dlq_producer: FromDishka[DlqProducerProtocol],
) -> tuple[Response, int]:
    """
    Internal endpoint for pipeline dependency resolution.

    Called by BOS to resolve pipeline dependencies and determine
    the optimal execution sequence for a requested pipeline.
    """
    try:
        # Parse and validate request
        request_data = await request.get_json()
        pipeline_request = BCSPipelineDefinitionRequestV1.model_validate(request_data)

        logger.info(
            "Processing pipeline resolution request",
            extra={
                "batch_id": pipeline_request.batch_id,
                "requested_pipeline": pipeline_request.requested_pipeline,
            },
        )

        # Resolve pipeline through service (includes DLQ production and metrics)
        response_data = await pipeline_service.resolve_pipeline_request(pipeline_request)

        # Check if resolution was successful (empty pipeline indicates failure)
        if not response_data.final_pipeline:
            logger.warning(
                f"Pipeline resolution failed: {response_data.analysis_summary}",
                extra={
                    "batch_id": response_data.batch_id,
                    "requested_pipeline": pipeline_request.requested_pipeline,
                },
            )
            return jsonify(
                {"error": "Pipeline resolution failed", "detail": response_data.analysis_summary}
            ), 400

        logger.info(
            "Pipeline resolution completed successfully",
            extra={
                "batch_id": response_data.batch_id,
                "final_pipeline_length": len(response_data.final_pipeline),
                "final_pipeline": response_data.final_pipeline,
            },
        )

        return jsonify(response_data.model_dump()), 200

    except ValidationError as err:
        # Bad request – validation error
        logger.warning("Invalid pipeline request", exc_info=True)
        return jsonify({"detail": err.errors()}), 400

    except Exception as e:
        logger.error(f"Unexpected error during pipeline resolution: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@pipeline_bp.route("/internal/v1/phases/complete", methods=["POST"])
@inject
async def record_phase_completion(
    batch_state_repo: FromDishka[BatchStateRepositoryProtocol],
) -> tuple[Response, int]:
    """
    TEST/OPS ENDPOINT ONLY - NOT FOR PRODUCTION USE.

    Internal endpoint for manually recording phase completion during testing and operations.
    In production, phase completions are recorded automatically via Kafka events.

    WARNING: This endpoint bypasses normal event flow and should only be used for:
    - Integration testing of multi-pipeline scenarios
    - Manual operational intervention during incident recovery
    - Development and debugging

    Production phase tracking occurs through Kafka event handlers only.
    """
    try:
        # Parse and validate request
        request_data = await request.get_json()

        # Extract required fields
        batch_id = request_data.get("batch_id")
        phase_name = request_data.get("phase_name")
        success = request_data.get("success", True)

        # Validate required fields
        if not batch_id or not phase_name:
            logger.warning(
                "Missing required fields in phase completion request",
                extra={"request_data": request_data},
            )
            return jsonify({"error": "Missing required fields: batch_id and phase_name"}), 400

        logger.info(
            f"Recording phase completion: {phase_name} for batch {batch_id}",
            extra={
                "batch_id": batch_id,
                "phase_name": phase_name,
                "success": success,
            },
        )

        # For batch-level phase completion, we record a single "batch-level" essay
        # This simplifies tracking since BOS doesn't know individual essay IDs
        # The key point is that the phase is marked complete for dependency resolution
        batch_level_essay_id = f"batch_{batch_id}_aggregate"

        # Record the phase completion
        result = await batch_state_repo.record_essay_step_completion(
            batch_id=batch_id,
            essay_id=batch_level_essay_id,
            step_name=phase_name,
            metadata={
                "success": success,
                "recorded_by": "BOS",
                "is_batch_level": True,
            },
        )

        if result:
            logger.info(
                f"Successfully recorded phase completion: {phase_name} for batch {batch_id}",
                extra={
                    "batch_id": batch_id,
                    "phase_name": phase_name,
                },
            )
            return jsonify(
                {
                    "status": "recorded",
                    "batch_id": batch_id,
                    "phase_name": phase_name,
                }
            ), 200
        else:
            logger.error(
                "Failed to record phase completion in repository",
                extra={
                    "batch_id": batch_id,
                    "phase_name": phase_name,
                },
            )
            return jsonify({"error": "Failed to record phase completion"}), 500

    except Exception as e:
        logger.error(
            f"Unexpected error during phase completion recording: {e}",
            extra={
                "error": str(e),
            },
            exc_info=True,
        )
        return jsonify({"error": "Internal server error"}), 500
