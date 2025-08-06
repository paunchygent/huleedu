"""Default implementation of ContentClientProtocol."""

from __future__ import annotations

from uuid import UUID

import aiohttp
from huleedu_service_libs.logging_utils import create_service_logger

# OpenTelemetry tracing handled by HuleEduError automatically
from services.spellchecker_service.http_operations import default_fetch_content_impl
from services.spellchecker_service.protocols import ContentClientProtocol

logger = create_service_logger("spellchecker_service.content_client_impl")


class DefaultContentClient(ContentClientProtocol):
    """Default implementation of ContentClientProtocol with structured error handling."""

    def __init__(self, content_service_url: str) -> None:
        self.content_service_url = content_service_url

    async def fetch_content(
        self,
        storage_id: str,
        http_session: aiohttp.ClientSession,
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> str:
        """Fetch content from Content Service using shared HTTP implementation.

        Args:
            storage_id: Content storage identifier
            http_session: HTTP client session
            correlation_id: Request correlation ID for tracing
            essay_id: Optional essay ID for logging context

        Returns:
            Content as string

        Raises:
            HuleEduError: On any failure to fetch content
        """
        return await default_fetch_content_impl(
            session=http_session,
            storage_id=storage_id,
            content_service_url=self.content_service_url,
            correlation_id=correlation_id,
            essay_id=essay_id,
        )
