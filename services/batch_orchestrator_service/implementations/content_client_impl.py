from __future__ import annotations

from uuid import UUID

import aiohttp
from huleedu_service_libs.error_handling import raise_external_service_error
from huleedu_service_libs.logging_utils import create_service_logger

from services.batch_orchestrator_service.config import Settings
from services.batch_orchestrator_service.protocols import ContentClientProtocol

logger = create_service_logger("bos.content_client")


class ContentClientImpl(ContentClientProtocol):
    """Lightweight Content Service client for prompt existence checks."""

    def __init__(self, session: aiohttp.ClientSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._base_url = settings.CONTENT_SERVICE_URL.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=settings.CONTENT_SERVICE_TIMEOUT_SECONDS)

    async def content_exists(self, storage_id: str, correlation_id: UUID) -> bool:
        """Return True if content exists (HTTP 200), False on 404, raise otherwise."""
        endpoint = f"{self._base_url}/{storage_id}"
        try:
            async with self._session.get(endpoint, timeout=self._timeout) as response:
                if response.status == 200:
                    logger.info(
                        "Content Service validation succeeded",
                        extra={
                            "operation": "content_exists",
                            "storage_id": storage_id,
                            "correlation_id": str(correlation_id),
                            "content_validation_result": "exists",
                        },
                    )
                    return True

                if response.status == 404:
                    logger.warning(
                        "Content Service reference not found",
                        extra={
                            "operation": "content_exists",
                            "storage_id": storage_id,
                            "correlation_id": str(correlation_id),
                            "content_validation_result": "not_found",
                        },
                    )
                    return False

                error_text = await response.text()
                raise_external_service_error(
                    service="batch_orchestrator_service",
                    operation="content_exists",
                    external_service="content_service",
                    message="Content Service returned unexpected status",
                    correlation_id=correlation_id,
                    status_code=response.status,
                    error_text=error_text[:500],
                    storage_id=storage_id,
                    content_validation_result="external_error",
                )
        except aiohttp.ClientError as exc:
            raise_external_service_error(
                service="batch_orchestrator_service",
                operation="content_exists",
                external_service="content_service",
                message="Content Service request failed",
                correlation_id=correlation_id,
                error_type=exc.__class__.__name__,
                storage_id=storage_id,
                content_validation_result="external_error",
            )
