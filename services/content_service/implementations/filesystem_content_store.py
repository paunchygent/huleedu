"""Filesystem-based content storage implementation."""

from __future__ import annotations

import uuid
from pathlib import Path
from uuid import UUID

import aiofiles
import aiofiles.os
from huleedu_service_libs.error_handling import (
    raise_content_service_error,
    raise_resource_not_found,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.content_service.protocols import ContentStoreProtocol

logger = create_service_logger("content.store.filesystem")


class FileSystemContentStore(ContentStoreProtocol):
    """Filesystem-based implementation of content storage."""

    def __init__(self, store_root: Path) -> None:
        """
        Initialize filesystem content store.

        Args:
            store_root: Root directory for content storage
        """
        self.store_root = store_root

    async def save_content(self, content_data: bytes, correlation_id: UUID) -> str:
        """
        Save content data and return storage identifier.

        Args:
            content_data: Raw bytes to store
            correlation_id: Request correlation ID for tracing

        Returns:
            Storage identifier (UUID hex string)

        Raises:
            HuleEduError: If storage operation fails
        """
        content_id = uuid.uuid4().hex
        file_path = self.store_root / content_id

        try:
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(content_data)

            logger.info(
                f"Stored content with ID: {content_id} at {file_path.resolve()}",
                extra={"correlation_id": str(correlation_id)},
            )
            return content_id
        except Exception as e:
            logger.error(
                f"Failed to store content: {e}",
                extra={"correlation_id": str(correlation_id)},
                exc_info=True,
            )
            raise_content_service_error(
                service="content_service",
                operation="save_content",
                message=f"Failed to store content: {str(e)}",
                correlation_id=correlation_id,
                file_path=str(file_path),
            )

    async def get_content_path(self, content_id: str, correlation_id: UUID) -> Path:
        """
        Get file path for content identifier.

        Args:
            content_id: Storage identifier
            correlation_id: Request correlation ID for tracing

        Returns:
            Path to content file

        Raises:
            HuleEduError: If content not found
        """
        file_path = self.store_root / content_id

        if not await aiofiles.os.path.isfile(str(file_path)):
            logger.warning(
                f"Content not found for ID: {content_id}",
                extra={"correlation_id": str(correlation_id)},
            )
            raise_resource_not_found(
                service="content_service",
                operation="get_content_path",
                resource_type="content",
                resource_id=content_id,
                correlation_id=correlation_id,
            )

        return file_path

    async def content_exists(self, content_id: str, correlation_id: UUID) -> bool:
        """
        Check if content exists for given identifier.

        Args:
            content_id: Storage identifier
            correlation_id: Request correlation ID for tracing

        Returns:
            True if content exists, False otherwise
        """
        file_path = self.store_root / content_id
        exists = bool(await aiofiles.os.path.isfile(str(file_path)))

        logger.debug(
            f"Content exists check for ID {content_id}: {exists}",
            extra={"correlation_id": str(correlation_id)},
        )

        return exists
