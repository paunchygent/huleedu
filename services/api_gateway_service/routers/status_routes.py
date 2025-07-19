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

router = APIRouter()
logger = create_service_logger("api_gateway.status_routes")


@router.get("/test/no-auth")
@inject
async def test_no_auth(
    http_client: FromDishka[HttpClientProtocol],
    metrics: FromDishka[MetricsProtocol],
):
    """Test endpoint without authentication."""
    return {"message": "Success - no auth required"}


@router.get("/test/with-auth")
@inject
async def test_with_auth(
    user_id: FromDishka[str],
):
    """Test endpoint with authentication."""
    return {"message": f"Success - authenticated as {user_id}"}


class BatchStatusResponse(BaseModel):
    """Response model for batch status requests."""

    status: BatchClientStatus = Field(..., description="The current status of the batch.")
    details: dict = Field(..., description="The detailed status information.")


@router.get("/batches/{batch_id}/status", response_model=BatchStatusResponse)
@inject
async def get_batch_status(
    batch_id: str,
    http_client: FromDishka[HttpClientProtocol],
    metrics: FromDishka[MetricsProtocol],
    user_id: FromDishka[str],  # Provided by AuthProvider.provide_user_id
    correlation_id: FromDishka[UUID],  # Provided by AuthProvider.provide_correlation_id
):
    """Get batch status with strict ownership enforcement.

    Acts as a pure proxy to the Result Aggregator Service which handles all
    status aggregation and any necessary fallback logic internally.
    """
    endpoint = f"/batches/{batch_id}/status"

    logger.info(
        f"Batch status request: batch_id='{batch_id}', user_id='{user_id}', correlation_id='{correlation_id}'"
    )

    with metrics.http_request_duration_seconds.labels(method="GET", endpoint=endpoint).time():
        try:
            aggregator_url = (
                f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{batch_id}/status"
            )

            # Time the downstream service call
            with metrics.downstream_service_call_duration_seconds.labels(
                service="result_aggregator", method="GET", endpoint="/internal/v1/batches/status"
            ).time():
                response = await http_client.get(aggregator_url)
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

            # Remove internal user_id from client response
            data.pop("user_id", None)
            metrics.http_requests_total.labels(
                method="GET", endpoint=endpoint, http_status="200"
            ).inc()
            return BatchStatusResponse(status=BatchClientStatus.AVAILABLE, details=data)

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
