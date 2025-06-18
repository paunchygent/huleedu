"""Pipeline resolution routes for Batch Conductor Service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dishka import FromDishka
from pydantic import ValidationError
from quart import Blueprint, Response, current_app, jsonify, request
from quart_dishka import inject

from huleedu_service_libs.logging_utils import create_service_logger
from services.batch_conductor_service.api_models import (
    BCSPipelineDefinitionRequestV1,
)
from services.batch_conductor_service.protocols import (
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
        # Inject metrics into pipeline service if available
        metrics_ext = current_app.extensions.get("metrics")
        if metrics_ext and hasattr(pipeline_service, "set_metrics"):
            pipeline_service.set_metrics(metrics_ext)

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
