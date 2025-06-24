"""Default implementation of ResultStoreProtocol."""

from __future__ import annotations

import aiohttp

from common_core.domain_enums import ContentType
from services.spell_checker_service.core_logic import default_store_content_impl
from services.spell_checker_service.protocols import ResultStoreProtocol


class DefaultResultStore(ResultStoreProtocol):
    """Default implementation of ResultStoreProtocol."""

    def __init__(self, content_service_url: str):
        self.content_service_url = content_service_url

    async def store_content(
        self,
        original_storage_id: str,
        content_type: ContentType,
        content: str,
        http_session: aiohttp.ClientSession,
    ) -> str:
        """Store content using the core logic implementation."""
        result = await default_store_content_impl(http_session, content, self.content_service_url)
        return str(result)
