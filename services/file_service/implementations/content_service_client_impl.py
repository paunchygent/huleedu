"""Content Service client implementation for File Service."""

from __future__ import annotations

from aiohttp import ClientSession
from huleedu_service_libs.logging_utils import create_service_logger

from common_core.domain_enums import ContentType
from services.file_service.config import Settings
from services.file_service.protocols import ContentServiceClientProtocol

logger = create_service_logger("file_service.implementations.content_service_client")


class DefaultContentServiceClient(ContentServiceClientProtocol):
    """Default implementation of ContentServiceClientProtocol."""

    def __init__(self, http_session: ClientSession, settings: Settings):
        self.http_session = http_session
        self.settings = settings

    async def store_content(self, content_bytes: bytes, content_type: ContentType) -> str:
        """Store content in Content Service and return storage ID."""
        try:
            # Content Service expects raw bytes data in request body
            async with self.http_session.post(
                self.settings.CONTENT_SERVICE_URL,
                data=content_bytes,
            ) as response:
                if response.status == 201:
                    result = await response.json()
                    storage_id = result.get("storage_id")
                    if isinstance(storage_id, str) and storage_id:
                        logger.info(
                            f"Successfully stored content (type: {content_type.value}), "
                            f"storage_id: {storage_id}",
                        )
                        return storage_id
                    else:
                        raise ValueError("Content Service response missing storage_id")
                else:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Content Service returned status {response.status}: {error_text}",
                    )
        except Exception as e:
            logger.error(f"Error storing content in Content Service: {e}")
            raise
