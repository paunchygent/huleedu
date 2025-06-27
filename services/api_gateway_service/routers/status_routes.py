from uuid import uuid4

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, HTTPException, Request, status
from httpx import AsyncClient, HTTPStatusError
from pydantic import BaseModel, Field

from huleedu_service_libs.logging_utils import create_service_logger

from .. import auth
from ..config import settings
from common_core.status_enums import BatchClientStatus



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
    user_id: str = Depends(auth.get_current_user_id),
):
    """Get batch status with strict ownership enforcement."""
    correlation_id = getattr(request.state, "correlation_id", None) or str(uuid4())
    logger.info(
        f"Batch status request: batch_id='{batch_id}', user_id='{user_id}', correlation_id='{correlation_id}'"
    )

    aggregator_url = f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{batch_id}/status"

    try:
        response = await http_client.get(aggregator_url)
        response.raise_for_status()
        data = response.json()

        # Enforce ownership check
        if data.get("user_id") != user_id:
            logger.warning(
                f"Ownership violation: batch '{batch_id}' does not belong to user '{user_id}'."
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # Remove internal user_id from client response
        data.pop("user_id", None)
        return BatchStatusResponse(status=BatchClientStatus.AVAILABLE, details=data)

    except HTTPStatusError as e:
        if e.response.status_code == 404 and settings.HANDLE_MISSING_BATCHES == "query_bos":
            logger.info(f"Batch not in aggregator, checking BOS: {batch_id}")
            bos_url = f"{settings.BOS_URL}/internal/v1/batches/{batch_id}/pipeline-state"
            try:
                bos_response = await http_client.get(bos_url)
                bos_response.raise_for_status()
                bos_data = bos_response.json()
                if bos_data.get("user_id") != user_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
                    )
                return BatchStatusResponse(
                    status=BatchClientStatus.PROCESSING, details=bos_data
                )
            except HTTPStatusError as bos_e:
                logger.error(f"BOS fallback failed for batch {batch_id}: {bos_e}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found"
                ) from bos_e

        logger.error(f"Aggregator service error for batch {batch_id}: {e}")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text) from e

    except Exception as e:
        logger.error(f"Unexpected error for batch {batch_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error"
        ) from e
