"""RAS (Result Aggregator Service) HTTP client."""

from __future__ import annotations

from uuid import UUID

import httpx
from huleedu_service_libs.logging_utils import create_service_logger

from services.bff_teacher_service.clients._utils import build_internal_auth_headers
from services.bff_teacher_service.config import settings
from services.bff_teacher_service.dto.teacher_v1 import BatchSummaryV1

logger = create_service_logger("bff_teacher.ras_client")


class RASClientImpl:
    """HTTP client for Result Aggregator Service internal API."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        """Initialize with shared HTTP client.

        Args:
            http_client: Shared httpx AsyncClient instance
        """
        self._client = http_client

    async def get_batches_for_user(
        self,
        user_id: str,
        correlation_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
    ) -> tuple[list[BatchSummaryV1], dict]:
        """Get batches for a user from RAS.

        Args:
            user_id: User ID to query batches for
            correlation_id: Request correlation ID
            limit: Max batches to return (default 20)
            offset: Pagination offset (default 0)
            status: Optional status filter (internal status value)

        Returns:
            Tuple of (list of BatchSummaryV1, pagination dict)

        Raises:
            httpx.HTTPStatusError: On HTTP errors from RAS
        """
        params: dict[str, int | str] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status

        url = f"{settings.RAS_URL}/internal/v1/batches/user/{user_id}"
        headers = build_internal_auth_headers(correlation_id)

        logger.debug(
            "Fetching batches from RAS",
            extra={"user_id": user_id, "correlation_id": str(correlation_id)},
        )

        response = await self._client.get(url, params=params, headers=headers)
        response.raise_for_status()

        data = response.json()
        batches_raw = data.get("batches", [])
        pagination = data.get("pagination", {"limit": limit, "offset": offset, "total": 0})

        batches = [BatchSummaryV1.model_validate(b) for b in batches_raw]

        logger.info(
            "Fetched batches from RAS",
            extra={
                "user_id": user_id,
                "batch_count": len(batches),
                "correlation_id": str(correlation_id),
            },
        )

        return batches, pagination
