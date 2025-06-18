"""Pipeline resolution routes for Batch Conductor Service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dishka import FromDishka

# Import protocol at runtime; Dishka resolves type hints using get_type_hints,
# so the symbol must exist at import time. We also assign it to a dummy var so
# Ruff treats it as used without ignore comments.
from services.batch_conductor_service.protocols import DlqProducerProtocol

_DLP_REF: type[DlqProducerProtocol] = DlqProducerProtocol

if TYPE_CHECKING:
    from services.batch_conductor_service.protocols import DlqProducerProtocol
from pydantic import ValidationError
from quart import Blueprint, Response, current_app, jsonify, request
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

        # Resolve pipeline through service
        response_data = await pipeline_service.resolve_pipeline_request(pipeline_request)

        # Metrics – success (skip if metrics not initialised)
        metrics_ext = current_app.extensions.get("metrics")
        if metrics_ext:
            metrics_ext["pipeline_resolutions"].labels(
                requested_pipeline=pipeline_request.requested_pipeline, status="success",
            ).inc()

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

    except ValueError as e:
        # Dependency error – produce DLQ and mark metric
        await dlq_producer.publish(
            envelope=pipeline_request.model_dump(),
            reason="PipelineValidationError",
        )

        metrics_ext = current_app.extensions.get("metrics")
        if metrics_ext:
            metrics_ext["pipeline_resolutions"].labels(
                requested_pipeline=pipeline_request.requested_pipeline, status="failure",
            ).inc()

        logger.warning(f"Invalid pipeline resolution request: {e}")
        return jsonify({"error": "Invalid request", "detail": str(e)}), 400

    except ConnectionError as e:
        logger.error(f"ELS connection error during pipeline resolution: {e}")
        return jsonify({"error": "External service unavailable", "detail": str(e)}), 503

    except Exception as e:
        # Push to DLQ for any unexpected errors
        try:
            await dlq_producer.publish(
                envelope=pipeline_request.model_dump() if "pipeline_request" in locals() else {},
                reason="InternalError",
            )
        except Exception as dlq_err:  # pragma: no cover – swallow dlq error to avoid masking original
            logger.error(f"Failed emitting DLQ for internal error: {dlq_err}")

        metrics_ext = current_app.extensions.get("metrics")
        if metrics_ext:
            metrics_ext["pipeline_resolutions"].labels(
                requested_pipeline=pipeline_request.requested_pipeline if "pipeline_request" in locals() else "unknown",
                status="error",
            ).inc()

        logger.error(f"Unexpected error during pipeline resolution: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
