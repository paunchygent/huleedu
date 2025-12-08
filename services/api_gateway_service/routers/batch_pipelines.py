"""Batch pipeline execution routes for API Gateway Service.

Handles pipeline execution commands with Kafka publishing:
- POST /batches/{batch_id}/pipelines - Request pipeline execution
"""

from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.client_commands import ClientBatchPipelineRequestV1
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.error_handling import raise_kafka_publish_error, raise_validation_error
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.logging_utils import create_service_logger

from ..app.rate_limiter import limiter
from ..config import settings
from ..protocols import HttpClientProtocol, MetricsProtocol
from ._batch_utils import BatchPipelineRequest

router = APIRouter()
logger = create_service_logger("api_gateway.batch_pipelines")


@router.post(
    "/batches/{batch_id}/pipelines",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request Pipeline Execution",
    description="Submit a batch for processing through the specified pipeline phase",
    response_description="Pipeline execution request accepted and queued",
    responses={
        202: {"description": "Request accepted and queued for processing"},
        400: {"description": "Invalid request parameters"},
        401: {"description": "Authentication required"},
        403: {"description": "Access forbidden - user does not own this batch"},
        429: {"description": "Rate limit exceeded"},
        503: {"description": "Service temporarily unavailable"},
    },
)
@limiter.limit("20/minute")
@inject
async def request_pipeline_execution(
    batch_id: str,
    request: Request,
    pipeline_request: BatchPipelineRequest,
    http_client: FromDishka[HttpClientProtocol],
    kafka_bus: FromDishka[KafkaBus],
    metrics: FromDishka[MetricsProtocol],
    user_id: FromDishka[str],
    org_id: FromDishka[str | None],
    correlation_id: FromDishka[UUID],
):
    """Request pipeline execution for a batch.

    Validates the request, performs preflight checks with BOS, and publishes
    the pipeline execution request to Kafka for asynchronous processing.

    **Authentication**: Requires valid JWT token (Bearer format)
    **Rate Limiting**: 20 requests per minute per user
    """
    endpoint = f"/batches/{batch_id}/pipelines"

    with metrics.http_request_duration_seconds.labels(method="POST", endpoint=endpoint).time():
        try:
            # Validate batch_id consistency
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

            # Preflight: Ask BOS to resolve pipeline and evaluate credits
            preflight_url = (
                f"{settings.BOS_URL}/internal/v1/batches/{batch_id}/pipelines/"
                f"{pipeline_request.requested_pipeline.value}/preflight"
            )
            pre_headers = {"X-Correlation-ID": str(correlation_id)}
            pre_resp = await http_client.post(
                preflight_url, json={}, headers=pre_headers, timeout=10.0
            )

            # If preflight denied, return appropriate status
            if pre_resp.status_code in (402, 429, 400, 404, 500):
                try:
                    body = pre_resp.json()
                except Exception:
                    body = {"detail": "Invalid response from BOS preflight"}

                status_to_return = 503 if pre_resp.status_code == 500 else pre_resp.status_code

                logger.info(
                    "Preflight blocked pipeline request",
                    extra={
                        "batch_id": batch_id,
                        "user_id": user_id,
                        "org_id": org_id,
                        "correlation_id": str(correlation_id),
                        "preflight_status": pre_resp.status_code,
                    },
                )
                return JSONResponse(status_code=status_to_return, content=body)

            # Construct event with authenticated user_id
            client_request = ClientBatchPipelineRequestV1(
                batch_id=batch_id,
                requested_pipeline=pipeline_request.requested_pipeline.value,
                client_correlation_id=correlation_id,
                user_id=user_id,
                is_retry=pipeline_request.is_retry,
                retry_reason=pipeline_request.retry_reason,
                prompt_payload=pipeline_request.prompt_payload,
            )

            # Create EventEnvelope with trace context
            from huleedu_service_libs.observability import inject_trace_context

            envelope = EventEnvelope[ClientBatchPipelineRequestV1](
                event_type=topic_name(ProcessingEvent.CLIENT_BATCH_PIPELINE_REQUEST),
                source_service="api_gateway_service",
                correlation_id=correlation_id,
                data=client_request,
                metadata={},
            )

            if envelope.metadata is not None:
                inject_trace_context(envelope.metadata)
                if org_id:
                    envelope.metadata["org_id"] = org_id

            # Publish to Kafka
            await kafka_bus.publish(
                topic=topic_name(ProcessingEvent.CLIENT_BATCH_PIPELINE_REQUEST),
                envelope=envelope,
                key=batch_id,
            )

            metrics.events_published_total.labels(
                topic=topic_name(ProcessingEvent.CLIENT_BATCH_PIPELINE_REQUEST),
                event_type=topic_name(ProcessingEvent.CLIENT_BATCH_PIPELINE_REQUEST),
            ).inc()

            logger.info(
                f"Pipeline request published: batch_id='{batch_id}', "
                f"pipeline='{client_request.requested_pipeline}', "
                f"user_id='{user_id}', org_id='{org_id}', correlation_id='{correlation_id}'"
            )

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
            from huleedu_service_libs.error_handling import HuleEduError

            if isinstance(e, HuleEduError):
                raise

            logger.error(
                f"Failed to publish pipeline request: batch_id='{batch_id}', "
                f"user_id='{user_id}', org_id='{org_id}', "
                f"correlation_id='{correlation_id}', error='{e}'",
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
                topic=topic_name(ProcessingEvent.CLIENT_BATCH_PIPELINE_REQUEST),
                message=f"Failed to publish pipeline request: {str(e)}",
                correlation_id=correlation_id,
                batch_id=batch_id,
                user_id=user_id,
            )
