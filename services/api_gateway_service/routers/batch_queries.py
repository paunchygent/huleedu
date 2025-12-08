"""Batch query routes for API Gateway Service.

Handles read-only batch queries:
- GET /batches - List user's batches with pagination and filtering
"""

from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query, Request
from httpx import HTTPStatusError

from huleedu_service_libs.error_handling import raise_external_service_error, raise_validation_error
from huleedu_service_libs.logging_utils import create_service_logger

from ..config import settings
from ..protocols import HttpClientProtocol, MetricsProtocol
from ._batch_utils import (
    CLIENT_TO_INTERNAL_STATUS,
    BatchListResponse,
    build_internal_auth_headers,
    map_internal_to_client_status,
)

router = APIRouter()
logger = create_service_logger("api_gateway.batch_queries")


@router.get(
    "/batches",
    response_model=BatchListResponse,
    summary="List User Batches",
    description="Retrieve paginated list of batches owned by the authenticated user",
    response_description="List of batches with pagination metadata",
    responses={
        200: {"description": "Batches retrieved successfully"},
        400: {"description": "Invalid request parameters"},
        401: {"description": "Authentication required"},
        503: {"description": "Service temporarily unavailable"},
    },
)
@inject
async def list_user_batches(
    request: Request,
    http_client: FromDishka[HttpClientProtocol],
    metrics: FromDishka[MetricsProtocol],
    user_id: FromDishka[str],
    correlation_id: FromDishka[UUID],
    limit: int = Query(default=20, ge=1, le=100, description="Maximum batches to return"),
    offset: int = Query(default=0, ge=0, description="Number of batches to skip"),
    status: str | None = Query(
        default=None,
        description=(
            "Filter by status: pending_content, ready, processing, "
            "completed_successfully, completed_with_failures, failed, cancelled"
        ),
    ),
):
    """List all batches owned by the authenticated user.

    **Authentication**: Requires valid JWT token (Bearer format)
    **Pagination**: Use `limit` and `offset` for pagination (default: 20 per page)
    **Status Filtering**: Filter by client-facing status values
    """
    endpoint = "/batches"

    logger.info(
        "Batch list request",
        extra={
            "user_id": user_id,
            "limit": limit,
            "offset": offset,
            "status": status,
            "correlation_id": str(correlation_id),
        },
    )

    with metrics.http_request_duration_seconds.labels(method="GET", endpoint=endpoint).time():
        # Validate status filter if provided
        if status and status not in CLIENT_TO_INTERNAL_STATUS:
            valid_statuses = ", ".join(CLIENT_TO_INTERNAL_STATUS.keys())
            raise_validation_error(
                service="api_gateway_service",
                operation="list_user_batches",
                field="status",
                message=f"Invalid status filter. Valid values: {valid_statuses}",
                correlation_id=correlation_id,
                value=status,
            )

        try:
            # Build RAS internal URL with query params
            query_params = f"?limit={limit}&offset={offset}"
            if status:
                # Use first internal status for MVP
                internal_statuses = CLIENT_TO_INTERNAL_STATUS[status]
                query_params += f"&status={internal_statuses[0]}"

            aggregator_url = (
                f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/user/{user_id}{query_params}"
            )

            # Build auth headers for internal service call
            headers = build_internal_auth_headers(correlation_id)

            # Time the downstream service call
            with metrics.downstream_service_call_duration_seconds.labels(
                service="result_aggregator",
                method="GET",
                endpoint="/internal/v1/batches/user/{user_id}",
            ).time():
                response = await http_client.get(aggregator_url, headers=headers)
                response.raise_for_status()
                data = response.json()

            metrics.downstream_service_calls_total.labels(
                service="result_aggregator",
                method="GET",
                endpoint="/internal/v1/batches/user/{user_id}",
                status_code=str(response.status_code),
            ).inc()

            # Map internal statuses to client statuses
            batches = data.get("batches", [])
            for batch in batches:
                if "overall_status" in batch:
                    batch["overall_status"] = map_internal_to_client_status(batch["overall_status"])
                batch.pop("user_id", None)

            metrics.http_requests_total.labels(
                method="GET", endpoint=endpoint, http_status="200"
            ).inc()

            return BatchListResponse(
                batches=batches,
                pagination=data.get(
                    "pagination", {"limit": limit, "offset": offset, "total": len(batches)}
                ),
            )

        except HTTPStatusError as e:
            logger.warning(
                "Result Aggregator Service error",
                extra={
                    "user_id": user_id,
                    "status_code": e.response.status_code,
                    "correlation_id": str(correlation_id),
                },
            )

            metrics.http_requests_total.labels(
                method="GET", endpoint=endpoint, http_status=str(e.response.status_code)
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=endpoint, error_type="downstream_service_error"
            ).inc()

            raise_external_service_error(
                service="api_gateway_service",
                operation="list_user_batches",
                external_service="result_aggregator",
                message=f"Failed to retrieve batches: {e.response.text}",
                correlation_id=correlation_id,
                status_code=e.response.status_code,
            )
