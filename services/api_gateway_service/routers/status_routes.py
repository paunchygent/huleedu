from __future__ import annotations

from uuid import uuid4

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, HTTPException, Request, status
from httpx import AsyncClient, HTTPStatusError
from pydantic import BaseModel, Field

from common_core.status_enums import BatchClientStatus
from huleedu_service_libs.logging_utils import create_service_logger
from services.api_gateway_service.config import settings

from .. import auth
from ..app.metrics import GatewayMetrics

router = APIRouter(route_class=DishkaRoute)
logger = create_service_logger("api_gateway.status_routes")


class BatchStatusResponse(BaseModel):
    """Response model for batch status requests."""

    status: BatchClientStatus = Field(..., description="The current status of the batch.")
    details: dict = Field(..., description="The detailed status information.")


@router.get("/batches/{batch_id}/status", response_model=BatchStatusResponse)
async def get_batch_status(
    request: Request,
    batch_id: str,
    http_client: FromDishka[AsyncClient],
    metrics: FromDishka[GatewayMetrics],
    user_id: str = Depends(auth.get_current_user_id),
):
    """Get batch status with strict ownership enforcement."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid4()))
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
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

            # Remove internal user_id from client response
            data.pop("user_id", None)
            metrics.http_requests_total.labels(
                method="GET", endpoint=endpoint, http_status="200"
            ).inc()
            return BatchStatusResponse(status=BatchClientStatus.AVAILABLE, details=data)

        except HTTPException:
            # Re-raise HTTPException without catching it
            raise
        except HTTPStatusError as e:
            # Pure proxy behavior - simply propagate downstream errors
            # RAS now handles BOS fallback internally for consistency
            logger.info(
                "Result Aggregator Service error",
                batch_id=batch_id,
                status_code=e.response.status_code,
                correlation_id=correlation_id
            )

            metrics.http_requests_total.labels(
                method="GET", endpoint=endpoint, http_status=str(e.response.status_code)
            ).inc()

            if e.response.status_code == 404:
                metrics.api_errors_total.labels(endpoint=endpoint, error_type="not_found").inc()
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found"
                ) from e
            else:
                metrics.api_errors_total.labels(
                    endpoint=endpoint, error_type="downstream_service_error"
                ).inc()
                raise HTTPException(
                    status_code=e.response.status_code, detail=e.response.text
                ) from e

        except Exception as e:
            logger.error(f"Unexpected error for batch {batch_id}: {e}", exc_info=True)
            metrics.http_requests_total.labels(
                method="GET", endpoint=endpoint, http_status="500"
            ).inc()
            metrics.api_errors_total.labels(endpoint=endpoint, error_type="internal_error").inc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error"
            ) from e
