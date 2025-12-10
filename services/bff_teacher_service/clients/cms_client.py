"""CMS (Class Management Service) HTTP client."""

from __future__ import annotations

from uuid import UUID

import httpx
from huleedu_service_libs.logging_utils import create_service_logger

from services.bff_teacher_service.clients._utils import build_internal_auth_headers
from services.bff_teacher_service.config import settings
from services.bff_teacher_service.dto.teacher_v1 import ClassInfoV1

logger = create_service_logger("bff_teacher.cms_client")


class CMSClientImpl:
    """HTTP client for Class Management Service internal API."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        """Initialize with shared HTTP client.

        Args:
            http_client: Shared httpx AsyncClient instance
        """
        self._client = http_client

    async def get_class_info_for_batches(
        self,
        batch_ids: list[UUID],
        correlation_id: UUID,
    ) -> dict[str, ClassInfoV1 | None]:
        """Get class info for multiple batches from CMS.

        Args:
            batch_ids: List of batch UUIDs to lookup
            correlation_id: Request correlation ID

        Returns:
            Dict mapping batch_id (str) to ClassInfoV1 or None

        Raises:
            httpx.HTTPStatusError: On HTTP errors from CMS
        """
        if not batch_ids:
            return {}

        batch_ids_param = ",".join(str(bid) for bid in batch_ids)
        url = f"{settings.CMS_URL}/internal/v1/batches/class-info"
        headers = build_internal_auth_headers(correlation_id)

        logger.debug(
            "Fetching class info from CMS",
            extra={"batch_count": len(batch_ids), "correlation_id": str(correlation_id)},
        )

        response = await self._client.get(
            url, params={"batch_ids": batch_ids_param}, headers=headers
        )
        response.raise_for_status()

        data = response.json()

        result: dict[str, ClassInfoV1 | None] = {}
        for batch_id, class_info in data.items():
            if class_info is not None:
                result[batch_id] = ClassInfoV1.model_validate(class_info)
            else:
                result[batch_id] = None

        logger.info(
            "Fetched class info from CMS",
            extra={
                "batch_count": len(batch_ids),
                "found_count": sum(1 for v in result.values() if v is not None),
                "correlation_id": str(correlation_id),
            },
        )

        return result
