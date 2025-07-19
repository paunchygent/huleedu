"""
Batch management routes for API Gateway Service.

Implements secure batch command processing using proper common_core contracts.
"""

from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field

from common_core.events.client_commands import ClientBatchPipelineRequestV1
from common_core.events.envelope import EventEnvelope
from common_core.pipeline_models import PhaseName
from huleedu_service_libs.error_handling import raise_kafka_publish_error, raise_validation_error
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.logging_utils import create_service_logger

from ..app.metrics import GatewayMetrics
from ..app.rate_limiter import limiter

router = APIRouter()
logger = create_service_logger("api_gateway.batch_routes")


class BatchPipelineRequest(BaseModel):
    """
    Input model for batch pipeline requests from API Gateway clients.

    This is separate from ClientBatchPipelineRequestV1 to avoid requiring
    user_id in the client request (it comes from authentication).
    """

    batch_id: str | None = Field(
        default=None,
        description="The unique identifier of the target batch (optional, taken from path).",
        min_length=1,
        max_length=255,
    )
    requested_pipeline: PhaseName = Field(
        description="The final pipeline phase the user wants to run."
    )
    is_retry: bool = Field(
        default=False,
        description="Flag indicating this is a user-initiated retry request.",
    )
    retry_reason: str | None = Field(
        default=None,
        description="Optional user-provided reason for the retry.",
        max_length=500,
    )


@router.post("/batches/{batch_id}/pipelines", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/minute")
@inject
async def request_pipeline_execution(
    request: Request,  # Required for rate limiting
    batch_id: str,
    pipeline_request: BatchPipelineRequest,
    kafka_bus: FromDishka[KafkaBus],
    metrics: FromDishka[GatewayMetrics],
    user_id: FromDishka[str],  # Provided by AuthProvider.provide_user_id
    correlation_id: FromDishka[UUID],  # Provided by AuthProvider.provide_correlation_id
):
    """
    Request pipeline execution for a batch with comprehensive validation and security.

    Uses proper ClientBatchPipelineRequestV1 contract from common_core and publishes
    events in EventEnvelope format to the correct Kafka topic.
    """
    endpoint = f"/batches/{batch_id}/pipelines"

    # Start request timing
    with metrics.http_request_duration_seconds.labels(method="POST", endpoint=endpoint).time():
        try:
            # CRITICAL: Validate batch_id consistency
            if pipeline_request.batch_id and pipeline_request.batch_id != batch_id:
                logger.warning(
                    f"Batch ID mismatch: path='{batch_id}', body='{pipeline_request.batch_id}', "
                    f"user_id='{user_id}', correlation_id='{correlation_id}'"
                )
                metrics.http_requests_total.labels(
                    method="POST", endpoint=endpoint, http_status="400"
                ).inc()
                metrics.api_errors_total.labels(
                    endpoint=endpoint, error_type="validation_error"
                ).inc()
                raise_validation_error(
                    service="api_gateway_service",
                    operation="request_pipeline_execution",
                    field="batch_id",
                    message="Batch ID in path must match batch ID in request body",
                    correlation_id=correlation_id,
                    value=pipeline_request.batch_id,
                    expected=batch_id,
                )

            # Construct ClientBatchPipelineRequestV1 with authenticated user_id
            client_request = ClientBatchPipelineRequestV1(
                batch_id=batch_id,  # Always use path batch_id
                requested_pipeline=pipeline_request.requested_pipeline.value,  # Convert enum to string
                client_correlation_id=correlation_id,
                user_id=user_id,  # From authentication
                is_retry=pipeline_request.is_retry,
                retry_reason=pipeline_request.retry_reason,
            )

            # Create proper EventEnvelope with ClientBatchPipelineRequestV1 data
            from huleedu_service_libs.observability import inject_trace_context

            envelope = EventEnvelope[ClientBatchPipelineRequestV1](
                event_type="huleedu.commands.batch.pipeline.v1",
                source_service="api_gateway_service",
                correlation_id=correlation_id,
                data=client_request,
                metadata={},
            )

            # Inject current trace context into the envelope metadata
            if envelope.metadata is not None:
                inject_trace_context(envelope.metadata)

            # Publish using KafkaBus.publish method with EventEnvelope
            await kafka_bus.publish(
                topic="huleedu.commands.batch.pipeline.v1",
                envelope=envelope,
                key=batch_id,  # Partition by batch_id for ordering
            )

            # Record successful event publication
            metrics.events_published_total.labels(
                topic="huleedu.commands.batch.pipeline.v1",
                event_type="huleedu.commands.batch.pipeline.v1",
            ).inc()

            # CRITICAL: Comprehensive logging for traceability
            logger.info(
                f"Pipeline request published: batch_id='{batch_id}', "
                f"pipeline='{client_request.requested_pipeline}', "
                f"user_id='{user_id}', correlation_id='{correlation_id}'"
            )

            # Record successful HTTP response
            metrics.http_requests_total.labels(
                method="POST", endpoint=endpoint, http_status="202"
            ).inc()

            return {
                "status": "accepted",
                "message": "Pipeline execution request received",
                "batch_id": batch_id,
                "correlation_id": str(correlation_id),
            }

        except Exception as e:
            logger.error(
                f"Failed to publish pipeline request: batch_id='{batch_id}', "
                f"user_id='{user_id}', correlation_id='{correlation_id}', error='{e}'",
                exc_info=True,
            )
            metrics.http_requests_total.labels(
                method="POST", endpoint=endpoint, http_status="503"
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=endpoint, error_type="kafka_publish_error"
            ).inc()
            raise_kafka_publish_error(
                service="api_gateway_service",
                operation="request_pipeline_execution",
                topic="huleedu.commands.batch.pipeline.v1",
                message=f"Failed to publish pipeline request: {str(e)}",
                correlation_id=correlation_id,
                batch_id=batch_id,
                user_id=user_id,
            )
