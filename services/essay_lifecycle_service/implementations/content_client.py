"""
Content client implementation for Essay Lifecycle Service.

Implements ContentClient protocol for HTTP-based content storage operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiohttp import ClientSession
    from common_core.enums import ContentType

    from config import Settings

from services.essay_lifecycle_service.protocols import ContentClient


class DefaultContentClient(ContentClient):
    """Default implementation of ContentClient protocol."""

    def __init__(self, http_session: ClientSession, settings: Settings) -> None:
        self.http_session = http_session
        self.settings = settings

    async def fetch_content(self, storage_id: str) -> bytes:
        """Fetch content from storage by ID."""
        url = f"{self.settings.CONTENT_SERVICE_URL}/fetch/{storage_id}"

        async with self.http_session.get(url) as response:
            response.raise_for_status()
            return await response.read()

    async def store_content(self, content: bytes, content_type: ContentType) -> str:
        """Store content and return storage ID."""
        url = f"{self.settings.CONTENT_SERVICE_URL}/store"

        data = {
            "content": content.decode("utf-8") if isinstance(content, bytes) else content,
            "content_type": content_type.value,
        }

        async with self.http_session.post(url, json=data) as response:
            response.raise_for_status()
            result = await response.json()
            return str(result["storage_id"])
