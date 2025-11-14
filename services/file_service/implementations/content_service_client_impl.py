"""Content Service client implementation for File Service."""

from __future__ import annotations

from uuid import UUID

from aiohttp import ClientSession
from common_core.domain_enums import ContentType
from huleedu_service_libs.error_handling import (
    raise_content_service_error,
    raise_external_service_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.file_service.config import Settings
from services.file_service.protocols import ContentServiceClientProtocol

logger = create_service_logger("file_service.implementations.content_service_client")


class DefaultContentServiceClient(ContentServiceClientProtocol):
    """Default implementation of ContentServiceClientProtocol."""

    def __init__(self, http_session: ClientSession, settings: Settings):
        self.http_session = http_session
        self.settings = settings

    async def store_content(
        self, content_bytes: bytes, content_type: ContentType, correlation_id: UUID
    ) -> str:
        """
        Store content in Content Service and return storage ID.

        Args:
            content_bytes: Raw binary content to store
            content_type: Type of content being stored
            correlation_id: Request correlation ID for tracing

        Returns:
            storage_id: Unique identifier for stored content

        Raises:
            HuleEduError: If storage operation fails
        """
        try:
            # TODO(TASK-CONTENT-SERVICE-IDEMPOTENT-UPLOADS): compute content hash and reuse existing
            # storage IDs once Content Service exposes lookup-or-create.
            # Content Service expects raw bytes data in request body
            headers = {"X-Correlation-ID": str(correlation_id)}
            async with self.http_session.post(
                self.settings.CONTENT_SERVICE_URL,
                data=content_bytes,
                headers=headers,
            ) as response:
                if response.status == 201:
                    result = await response.json()
                    storage_id = result.get("storage_id")
                    if isinstance(storage_id, str) and storage_id:
                        logger.info(
                            f"Successfully stored content (type: {content_type.value}), "
                            f"storage_id: {storage_id}",
                            extra={"correlation_id": str(correlation_id)},
                        )
                        return storage_id
                    else:
                        raise_content_service_error(
                            service="file_service",
                            operation="store_content",
                            message="Content Service response missing storage_id",
                            correlation_id=correlation_id,
                            response=result,
                        )
                else:
                    error_text = await response.text()
                    raise_external_service_error(
                        service="file_service",
                        operation="store_content",
                        external_service="content_service",
                        message=f"Content Service returned status {response.status}: {error_text}",
                        correlation_id=correlation_id,
                        status_code=response.status,
                    )
        except Exception as e:
            logger.error(
                f"Error storing content in Content Service: {e}",
                extra={"correlation_id": str(correlation_id)},
            )
            # Re-raise if already a HuleEduError
            if hasattr(e, "error_detail"):
                raise
            # Otherwise wrap in content service error
            raise_content_service_error(
                service="file_service",
                operation="store_content",
                message=f"Failed to store content: {str(e)}",
                correlation_id=correlation_id,
                error=str(e),
            )
