"""Pipeline resolution routes for Batch Conductor Service."""

from __future__ import annotations

from dishka import FromDishka
from quart import Blueprint, Response, jsonify, request
from quart_dishka import inject

from huleedu_service_libs.logging_utils import create_service_logger
from services.batch_conductor_service.api_models import (
    BCSPipelineDefinitionRequestV1,
)
from services.batch_conductor_service.protocols import PipelineResolutionServiceProtocol

logger = create_service_logger("bcs.api.pipeline")
pipeline_bp = Blueprint("pipeline_routes", __name__)


@pipeline_bp.route("/internal/v1/pipelines/define", methods=["POST"])
@inject
async def define_pipeline(
    pipeline_service: FromDishka[PipelineResolutionServiceProtocol],
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

        # Resolve pipeline through service
        response_data = await pipeline_service.resolve_pipeline_request(pipeline_request)

        logger.info(
            "Pipeline resolution completed successfully",
            extra={
                "batch_id": response_data.batch_id,
                "final_pipeline_length": len(response_data.final_pipeline),
                "final_pipeline": response_data.final_pipeline,
            },
        )

        return jsonify(response_data.model_dump()), 200

    except ValueError as e:
        logger.warning(f"Invalid pipeline resolution request: {e}")
        return jsonify({"error": "Invalid request", "detail": str(e)}), 400

    except ConnectionError as e:
        logger.error(f"ELS connection error during pipeline resolution: {e}")
        return jsonify({"error": "External service unavailable", "detail": str(e)}), 503

    except Exception as e:
        logger.error(f"Unexpected error during pipeline resolution: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
