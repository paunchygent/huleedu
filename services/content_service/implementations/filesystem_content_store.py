"""Filesystem-based content storage implementation."""

from __future__ import annotations

import uuid
from pathlib import Path

import aiofiles
import aiofiles.os
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

    async def save_content(self, content_data: bytes) -> str:
        """
        Save content data and return storage identifier.

        Args:
            content_data: Raw bytes to store

        Returns:
            Storage identifier (UUID hex string)

        Raises:
            Exception: If storage operation fails
        """
        content_id = uuid.uuid4().hex
        file_path = self.store_root / content_id

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content_data)

        logger.info(f"Stored content with ID: {content_id} at {file_path.resolve()}")
        return content_id

    async def get_content_path(self, content_id: str) -> Path:
        """
        Get file path for content identifier.

        Args:
            content_id: Storage identifier

        Returns:
            Path to content file
        """
        return self.store_root / content_id

    async def content_exists(self, content_id: str) -> bool:
        """
        Check if content exists for given identifier.

        Args:
            content_id: Storage identifier

        Returns:
            True if content exists, False otherwise
        """
        file_path = self.store_root / content_id
        return bool(await aiofiles.os.path.isfile(str(file_path)))
