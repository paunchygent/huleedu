"""
Batch management routes for API Gateway Service.

Implements secure batch command processing using proper common_core contracts.
"""

from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from common_core.api_models.batch_registration import BatchRegistrationRequestV1
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.client_commands import ClientBatchPipelineRequestV1
from common_core.events.envelope import EventEnvelope
from common_core.pipeline_models import PhaseName
from huleedu_service_libs.error_handling import raise_kafka_publish_error, raise_validation_error
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.logging_utils import create_service_logger

from ..app.metrics import GatewayMetrics
from ..app.rate_limiter import limiter
from ..config import settings
from ..protocols import HttpClientProtocol, MetricsProtocol

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


class ClientBatchRegistrationRequest(BaseModel):
    """Client-facing registration model (no identity fields).

    API Gateway enriches this with `user_id` and optional `org_id` from JWT
    and forwards it to BOS using the shared inter-service contract.
    """

    expected_essay_count: int = Field(..., gt=0)
    essay_ids: list[str] | None = Field(default=None, min_length=1)
    course_code: CourseCode
    essay_instructions: str
    class_id: str | None = None
    enable_cj_assessment: bool = False
    cj_default_llm_model: str | None = None
    cj_default_temperature: float | None = Field(default=None, ge=0.0, le=2.0)


@router.post(
    "/batches/register",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Register a new batch",
    description=(
        "Client-facing endpoint for batch registration. API Gateway injects identity "
        "(user_id/org_id) and proxies to the Batch Orchestrator Service."
    ),
)
@inject
async def register_batch(
    registration_request: ClientBatchRegistrationRequest,
    request: Request,
    http_client: FromDishka[HttpClientProtocol],
    metrics: FromDishka[MetricsProtocol],
    user_id: FromDishka[str],
    org_id: FromDishka[str | None],
    correlation_id: FromDishka[UUID],
):
    endpoint = "/batches/register"
    with metrics.http_request_duration_seconds.labels(method="POST", endpoint=endpoint).time():
        # Build inter-service contract with identity enrichment
        internal_model = BatchRegistrationRequestV1(
            expected_essay_count=registration_request.expected_essay_count,
            essay_ids=registration_request.essay_ids,
            course_code=registration_request.course_code,
            essay_instructions=registration_request.essay_instructions,
            user_id=user_id,
            org_id=org_id,
            class_id=registration_request.class_id,
            enable_cj_assessment=registration_request.enable_cj_assessment,
            cj_default_llm_model=registration_request.cj_default_llm_model,
            cj_default_temperature=registration_request.cj_default_temperature,
        )

        # Proxy to BOS with correlation header
        bos_url = f"{settings.BOS_URL}/v1/batches/register"
        response = await http_client.post(
            bos_url,
            json=internal_model.model_dump(mode="json"),
            headers={"X-Correlation-ID": str(correlation_id)},
            timeout=30.0,
        )

        # Pass through status and response body
        try:
            body = response.json()
        except Exception:
            body = {"detail": "Invalid response from BOS"}

        if response.status_code in (200, 202):
            logger.info(
                f"Batch registration proxied: user_id='{user_id}', org_id='{org_id}', correlation_id='{correlation_id}'"
            )
        else:
            logger.warning(
                f"BOS registration failed: status={response.status_code}, body={body}, correlation_id='{correlation_id}'"
            )
        return JSONResponse(status_code=response.status_code, content=body)


@router.post(
    "/batches/{batch_id}/pipelines",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request Pipeline Execution",
    description="Submit a batch for processing through the specified pipeline phase",
    response_description="Pipeline execution request accepted and queued",
    responses={
        202: {
            "description": "Request accepted and queued for processing",
            "content": {
                "application/json": {
                    "example": {
                        "status": "accepted",
                        "message": "Pipeline execution request received",
                        "batch_id": "batch_123",
                        "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                    }
                }
            },
        },
        400: {
            "description": "Invalid request parameters",
            "content": {
                "application/json": {
                    "examples": {
                        "batch_id_mismatch": {
                            "summary": "Batch ID mismatch between path and body",
                            "value": {
                                "error_type": "ValidationError",
                                "message": "Batch ID in path must match batch ID in request body",
                                "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                                "field": "batch_id",
                                "expected": "batch_123",
                                "received": "batch_456",
                            },
                        },
                        "invalid_pipeline": {
                            "summary": "Invalid pipeline phase specified",
                            "value": {
                                "error_type": "ValidationError",
                                "message": "Invalid pipeline phase",
                                "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                                "field": "requested_pipeline",
                                "allowed_values": [
                                    "SPELLCHECK",
                                    "CONTENT_JUDGMENT",
                                    "FEEDBACK_GENERATION",
                                ],
                            },
                        },
                    }
                }
            },
        },
        401: {
            "description": "Authentication required",
            "content": {
                "application/json": {
                    "example": {
                        "error_type": "AuthenticationError",
                        "message": "Valid JWT token required",
                        "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                    }
                }
            },
        },
        403: {
            "description": "Access forbidden - user does not own this batch",
            "content": {
                "application/json": {
                    "example": {
                        "error_type": "AuthorizationError",
                        "message": "User does not have permission to access this batch",
                        "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                        "batch_id": "batch_123",
                        "user_id": "user_456",
                    }
                }
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {
                "application/json": {
                    "example": {
                        "error_type": "RateLimitError",
                        "message": "Rate limit exceeded: 20 requests per minute",
                        "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                        "retry_after": 60,
                    }
                }
            },
        },
        503: {
            "description": "Service temporarily unavailable",
            "content": {
                "application/json": {
                    "example": {
                        "error_type": "KafkaPublishError",
                        "message": "Failed to publish pipeline request: Kafka broker unavailable",
                        "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                        "batch_id": "batch_123",
                        "retry_recommended": True,
                    }
                }
            },
        },
    },
)
@limiter.limit("20/minute")
@inject
async def request_pipeline_execution(
    batch_id: str,
    request: Request,  # Required for rate limiting
    pipeline_request: BatchPipelineRequest,
    http_client: FromDishka[HttpClientProtocol],
    kafka_bus: FromDishka[KafkaBus],
    metrics: FromDishka[GatewayMetrics],
    user_id: FromDishka[str],  # Provided by AuthProvider.provide_user_id
    org_id: FromDishka[str | None],  # Provided by AuthProvider.provide_org_id
    correlation_id: FromDishka[UUID],  # Provided by AuthProvider.provide_correlation_id
):
    """
    Request pipeline execution for a batch with comprehensive validation and security.

    This endpoint allows authenticated users to submit their batches for processing through
    the specified pipeline phase. The request is validated, authenticated, and then published
    to the appropriate Kafka topic for asynchronous processing.

    **Authentication**: Requires valid JWT token in Authorization header (Bearer format)
    - Identity Injection: `user_id` (required) and `org_id` (optional) are injected via DI.
    - Org Identity Handling: `org_id` is recorded in the event envelope metadata when present
      to support org-first attribution without changing the client command contract.

    **Rate Limiting**: 20 requests per minute per user

    **Processing Flow**:
    1. Validate batch ownership (user must own the batch)
    2. Validate pipeline phase is supported
    3. Publish request to Kafka for asynchronous processing
    4. Return immediate acknowledgment with correlation ID for tracking

    **Pipeline Phases**:
    - `SPELLCHECK`: Basic spelling and grammar validation
    - `CONTENT_JUDGMENT`: AI-powered content quality assessment
    - `FEEDBACK_GENERATION`: Generate detailed feedback for essays

    **Error Handling**:
    - Validation errors return 400 with detailed field information
    - Authentication failures return 401
    - Authorization failures (batch ownership) return 403
    - Rate limiting returns 429 with retry-after information
    - Service unavailability returns 503 with retry recommendation
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

            # Preflight: Ask BOS to resolve pipeline and evaluate credits before publishing
            preflight_url = (
                f"{settings.BOS_URL}/internal/v1/batches/{batch_id}/pipelines/"
                f"{pipeline_request.requested_pipeline.value}/preflight"
            )
            pre_headers = {"X-Correlation-ID": str(correlation_id)}
            pre_resp = await http_client.post(preflight_url, json={}, headers=pre_headers, timeout=10.0)

            # If insufficient credits or other denial, return appropriate status with details
            if pre_resp.status_code in (402, 429, 400, 404, 500):
                try:
                    body = pre_resp.json()
                except Exception:
                    body = {"detail": "Invalid response from BOS preflight"}

                # Map 500 from BOS to 503 to reflect downstream dependency status
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

            # Construct ClientBatchPipelineRequestV1 with authenticated user_id (preflight passed)
            client_request = ClientBatchPipelineRequestV1(
                batch_id=batch_id,  # Always use path batch_id
                requested_pipeline=(
                    pipeline_request.requested_pipeline.value
                ),  # Convert enum to string
                client_correlation_id=correlation_id,
                user_id=user_id,  # From authentication
                is_retry=pipeline_request.is_retry,
                retry_reason=pipeline_request.retry_reason,
            )

            # Create proper EventEnvelope with ClientBatchPipelineRequestV1 data
            from huleedu_service_libs.observability import inject_trace_context

            envelope = EventEnvelope[ClientBatchPipelineRequestV1](
                event_type=topic_name(ProcessingEvent.CLIENT_BATCH_PIPELINE_REQUEST),
                source_service="api_gateway_service",
                correlation_id=correlation_id,
                data=client_request,
                metadata={},
            )

            # Inject current trace context into the envelope metadata
            if envelope.metadata is not None:
                inject_trace_context(envelope.metadata)
                # Include org identity in metadata for downstream attribution (optional)
                if org_id:
                    envelope.metadata["org_id"] = org_id

            # Publish using KafkaBus.publish method with EventEnvelope
            await kafka_bus.publish(
                topic=topic_name(ProcessingEvent.CLIENT_BATCH_PIPELINE_REQUEST),
                envelope=envelope,
                key=batch_id,  # Partition by batch_id for ordering
            )

            # Record successful event publication
            metrics.events_published_total.labels(
                topic=topic_name(ProcessingEvent.CLIENT_BATCH_PIPELINE_REQUEST),
                event_type=topic_name(ProcessingEvent.CLIENT_BATCH_PIPELINE_REQUEST),
            ).inc()

            # CRITICAL: Comprehensive logging for traceability
            logger.info(
                f"Pipeline request published: batch_id='{batch_id}', "
                f"pipeline='{client_request.requested_pipeline}', "
                f"user_id='{user_id}', org_id='{org_id}', correlation_id='{correlation_id}'"
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
            # Let HuleEduError bubble up to error handlers
            from huleedu_service_libs.error_handling import HuleEduError

            if isinstance(e, HuleEduError):
                raise
            logger.error(
                f"Failed to publish pipeline request: batch_id='{batch_id}', "
                f"user_id='{user_id}', org_id='{org_id}', correlation_id='{correlation_id}', error='{e}'",
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
