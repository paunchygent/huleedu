from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter
from httpx import HTTPStatusError
from pydantic import BaseModel, Field

from common_core.status_enums import BatchClientStatus
from huleedu_service_libs.error_handling import (
    raise_authorization_error,
    raise_external_service_error,
    raise_resource_not_found,
)
from huleedu_service_libs.logging_utils import create_service_logger
from services.api_gateway_service.config import settings
from services.api_gateway_service.protocols import HttpClientProtocol, MetricsProtocol

from ._batch_utils import build_internal_auth_headers

router = APIRouter()
logger = create_service_logger("api_gateway.status_routes")


@router.get(
    "/test/no-auth",
    summary="Test Endpoint (No Auth)",
    description="Test endpoint for verifying API Gateway connectivity without authentication",
    responses={
        200: {
            "description": "Test successful",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Success - no auth required",
                        "timestamp": "2024-01-15T10:30:00Z",
                        "service": "api_gateway_service",
                    }
                }
            },
        }
    },
)
@inject
async def test_no_auth(
    http_client: FromDishka[HttpClientProtocol],
    metrics: FromDishka[MetricsProtocol],
):
    """
    Test endpoint for verifying API Gateway connectivity without authentication.

    This endpoint is useful for:
    - Health checks and monitoring
    - Verifying basic API Gateway functionality
    - Testing network connectivity
    - Load balancer health checks

    **No Authentication Required**: This endpoint bypasses authentication middleware
    """
    return {"message": "Success - no auth required"}


@router.get(
    "/test/with-auth",
    summary="Test Endpoint (With Auth)",
    description="Test endpoint for verifying authentication and JWT token validation",
    responses={
        200: {
            "description": "Authentication test successful",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Success - authenticated as user_123",
                        "user_id": "user_123",
                        "timestamp": "2024-01-15T10:30:00Z",
                        "token_valid": True,
                    }
                }
            },
        },
        401: {
            "description": "Authentication failed",
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
    },
)
@inject
async def test_with_auth(
    user_id: FromDishka[str],
):
    """
    Test endpoint for verifying authentication and JWT token validation.

    This endpoint is useful for:
    - Testing JWT token validity
    - Verifying authentication middleware
    - Debugging authentication issues
    - Client-side token validation

    **Authentication Required**: Requires valid JWT token in Authorization header

    **Returns**: User ID extracted from the validated JWT token
    """
    return {"message": f"Success - authenticated as {user_id}"}


class BatchStatusResponse(BaseModel):
    """Response model for batch status requests."""

    status: BatchClientStatus = Field(..., description="The current status of the batch.")
    details: dict = Field(..., description="The detailed status information.")


def map_to_client_status(internal_status: str | None) -> BatchClientStatus:
    """
    Map internal BatchStatus to client-facing BatchClientStatus.

    This function ensures consistency between backend processing states
    and client API responses. It groups internal states into meaningful
    client-facing categories that frontend developers can act upon.

    Args:
        internal_status: The internal BatchStatus value (lowercase string)

    Returns:
        BatchClientStatus: Corresponding client-facing status

    Mapping Logic:
    - Content validation states → PENDING_CONTENT
    - Ready states → READY
    - All processing phases → PROCESSING
    - Success completion → COMPLETED_SUCCESSFULLY
    - Partial completion → COMPLETED_WITH_FAILURES
    - Critical failures → FAILED
    - Cancellation → CANCELLED
    """
    if not internal_status:
        return BatchClientStatus.PENDING_CONTENT

    # Content validation and configuration states
    if internal_status in ["awaiting_content_validation", "awaiting_pipeline_configuration"]:
        return BatchClientStatus.PENDING_CONTENT

    # Content failure states
    if internal_status == "content_ingestion_failed":
        return BatchClientStatus.FAILED

    # Ready for processing
    if internal_status == "ready_for_pipeline_execution":
        return BatchClientStatus.READY

    # Active processing states
    if internal_status in [
        "processing_pipelines",
        "awaiting_student_validation",
        "student_validation_completed",
        "validation_timeout_processed",
    ]:
        return BatchClientStatus.PROCESSING

    # Terminal success states
    if internal_status == "completed_successfully":
        return BatchClientStatus.COMPLETED_SUCCESSFULLY

    if internal_status == "completed_with_failures":
        return BatchClientStatus.COMPLETED_WITH_FAILURES

    # Terminal failure states
    if internal_status == "failed_critically":
        return BatchClientStatus.FAILED

    if internal_status == "cancelled":
        return BatchClientStatus.CANCELLED

    # Fallback for any unmapped states
    logger.warning(f"Unknown internal status '{internal_status}', defaulting to PENDING_CONTENT")
    return BatchClientStatus.PENDING_CONTENT


@router.get(
    "/batches/{batch_id}/status",
    response_model=BatchStatusResponse,
    summary="Get Batch Status",
    description="Retrieve current status and processing details for a batch",
    response_description="Current batch status with detailed processing information",
    responses={
        200: {
            "description": "Batch status retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "processing",
                        "details": {
                            "batch_id": "batch_123",
                            "created_at": "2024-01-15T10:30:00Z",
                            "updated_at": "2024-01-15T10:45:00Z",
                            "total_essays": 5,
                            "processed_essays": 3,
                            "current_phase": "CONTENT_JUDGMENT",
                            "progress_percentage": 60,
                            "estimated_completion": "2024-01-15T11:15:00Z",
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
                        "message": "Ownership violation: batch does not belong to user",
                        "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                        "batch_id": "batch_123",
                        "requested_by": "user_456",
                        "actual_owner": "user_789",
                    }
                }
            },
        },
        404: {
            "description": "Batch not found",
            "content": {
                "application/json": {
                    "example": {
                        "error_type": "ResourceNotFoundError",
                        "message": "Batch not found",
                        "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                        "resource_type": "batch",
                        "resource_id": "batch_123",
                    }
                }
            },
        },
        503: {
            "description": "Service temporarily unavailable",
            "content": {
                "application/json": {
                    "example": {
                        "error_type": "ExternalServiceError",
                        "message": "Result Aggregator Service temporarily unavailable",
                        "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                        "external_service": "result_aggregator",
                        "retry_recommended": True,
                    }
                }
            },
        },
    },
)
@inject
async def get_batch_status(
    batch_id: str,
    http_client: FromDishka[HttpClientProtocol],
    metrics: FromDishka[MetricsProtocol],
    user_id: FromDishka[str],  # Provided by AuthProvider.provide_user_id
    correlation_id: FromDishka[UUID],  # Provided by AuthProvider.provide_correlation_id
):
    """
    Retrieve current status and processing details for a batch with strict ownership enforcement.

    This endpoint allows authenticated users to check the status of their batches, including
    processing progress, current phase, and estimated completion time. The endpoint enforces
    strict ownership validation to ensure users can only access their own batches.

    **Authentication**: Requires valid JWT token in Authorization header (Bearer format)

    **Ownership Enforcement**: Users can only access batches they own

    **Status Information Includes**:
    - Current processing phase (pending_content, ready, processing, completed_successfully, etc.)
    - Progress percentage and essay counts
    - Timestamps for creation and last update
    - Estimated completion time (when processing)
    - Error details (when failed)

    **Processing Phases**:
    - `pending_content`: Batch created, awaiting content validation or configuration
    - `ready`: Files uploaded and validated, ready for processing
    - `processing`: Currently being processed through pipeline
    - `completed_successfully`: All processing completed successfully
    - `completed_with_failures`: Processing completed but some essays failed
    - `failed`: Processing failed with critical errors
    - `cancelled`: Processing cancelled by user or system

    **Real-time Updates**:
    Status changes are also delivered via WebSocket notifications for real-time updates.
    The status values are identical between REST API and WebSocket for consistency.

    **Error Handling**:
    - Authentication failures return 401
    - Authorization failures (batch ownership) return 403
    - Missing batch returns 404
    - Service unavailability returns 503 with retry recommendation

    **Client Implementation Example**:
    ```javascript
    const response = await fetch(`/api/batches/${batchId}/status`, {
        headers: {
            'Authorization': 'Bearer ' + token
        }
    });

    const { status, details } = await response.json();
    console.log(`Batch ${details.batch_id} is ${status}`);

    // Handle completion states
    if (status === 'completed_successfully') {
        // All essays processed successfully
    } else if (status === 'completed_with_failures') {
        // Some essays failed, check details for specifics
    }
    ```
    """
    endpoint = f"/batches/{batch_id}/status"

    logger.info(
        f"Batch status request: batch_id='{batch_id}', user_id='{user_id}', "
        f"correlation_id='{correlation_id}'"
    )

    with metrics.http_request_duration_seconds.labels(method="GET", endpoint=endpoint).time():
        try:
            aggregator_url = (
                f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{batch_id}/status"
            )

            # Build auth headers for internal service call
            headers = build_internal_auth_headers(correlation_id)

            # Time the downstream service call
            with metrics.downstream_service_call_duration_seconds.labels(
                service="result_aggregator", method="GET", endpoint="/internal/v1/batches/status"
            ).time():
                response = await http_client.get(aggregator_url, headers=headers)
                response.raise_for_status()
                data = response.json()

            # Record downstream service call
            metrics.downstream_service_calls_total.labels(
                service="result_aggregator",
                method="GET",
                endpoint="/internal/v1/batches/status",
                status_code=str(response.status_code),
            ).inc()

            # Enforce ownership check
            if data.get("user_id") != user_id:
                logger.warning(
                    f"Ownership violation: batch '{batch_id}' does not belong to user '{user_id}'."
                )
                metrics.http_requests_total.labels(
                    method="GET", endpoint=endpoint, http_status="403"
                ).inc()
                metrics.api_errors_total.labels(endpoint=endpoint, error_type="access_denied").inc()
                raise_authorization_error(
                    service="api_gateway_service",
                    operation="get_batch_status",
                    message="Ownership violation: batch does not belong to user",
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                    requested_by=user_id,
                    actual_owner=data.get("user_id"),
                )

            # Extract actual status from RAS response and map to client status
            actual_status = data.get("overall_status")
            client_status = map_to_client_status(actual_status)

            logger.debug(
                f"Status mapping: internal='{actual_status}' → client='{client_status.value}'",
                batch_id=batch_id,
            )

            # Remove internal user_id from client response
            data.pop("user_id", None)
            metrics.http_requests_total.labels(
                method="GET", endpoint=endpoint, http_status="200"
            ).inc()
            return BatchStatusResponse(status=client_status, details=data)

        except HTTPStatusError as e:
            # Pure proxy behavior - simply propagate downstream errors
            # RAS now handles BOS fallback internally for consistency
            logger.info(
                "Result Aggregator Service error",
                batch_id=batch_id,
                status_code=e.response.status_code,
                correlation_id=correlation_id,
            )

            metrics.http_requests_total.labels(
                method="GET", endpoint=endpoint, http_status=str(e.response.status_code)
            ).inc()

            if e.response.status_code == 404:
                metrics.api_errors_total.labels(endpoint=endpoint, error_type="not_found").inc()
                raise_resource_not_found(
                    service="api_gateway_service",
                    operation="get_batch_status",
                    resource_type="batch",
                    resource_id=batch_id,
                    correlation_id=correlation_id,
                )
            else:
                metrics.api_errors_total.labels(
                    endpoint=endpoint, error_type="downstream_service_error"
                ).inc()
                raise_external_service_error(
                    service="api_gateway_service",
                    operation="get_batch_status",
                    external_service="result_aggregator",
                    message=f"Downstream service error: {e.response.text}",
                    correlation_id=correlation_id,
                    status_code=e.response.status_code,
                )
