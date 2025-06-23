"""Default implementation of ContentClientProtocol."""

from __future__ import annotations

import aiohttp

from services.spell_checker_service.core_logic import default_fetch_content_impl
from services.spell_checker_service.protocols import ContentClientProtocol


class DefaultContentClient(ContentClientProtocol):
    """Default implementation of ContentClientProtocol."""

    def __init__(self, content_service_url: str):
        self.content_service_url = content_service_url

    async def fetch_content(self, storage_id: str, http_session: aiohttp.ClientSession) -> str:
        """Fetch content using the core logic implementation."""
        result = await default_fetch_content_impl(
            http_session,
            storage_id,
            self.content_service_url,
        )
        return str(result)
