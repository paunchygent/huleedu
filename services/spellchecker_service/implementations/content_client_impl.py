"""Default implementation of ContentClientProtocol."""

from __future__ import annotations

from uuid import UUID

import aiohttp
from huleedu_service_libs.error_handling import raise_content_service_error
from huleedu_service_libs.logging_utils import create_service_logger

# OpenTelemetry tracing handled by HuleEduError automatically
from services.spellchecker_service.protocols import ContentClientProtocol

logger = create_service_logger("spellchecker_service.content_client_impl")


class DefaultContentClient(ContentClientProtocol):
    """Default implementation of ContentClientProtocol with structured error handling."""

    def __init__(self, content_service_url: str):
        self.content_service_url = content_service_url

    async def fetch_content(
        self,
        storage_id: str,
        http_session: aiohttp.ClientSession,
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> str:
        """Fetch content from Content Service with structured error handling.

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
        url = f"{self.content_service_url}/{storage_id}"
        log_prefix = f"Essay {essay_id}: " if essay_id else ""

        logger.debug(
            f"{log_prefix}Fetching content from URL: {url}",
            extra={"correlation_id": str(correlation_id), "storage_id": storage_id},
        )

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with http_session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    content = await response.text()
                    logger.debug(
                        f"{log_prefix}Successfully fetched content from {storage_id} "
                        f"(length: {len(content)})",
                        extra={"correlation_id": str(correlation_id), "storage_id": storage_id},
                    )
                    return content

                elif response.status == 404:
                    error_text = await response.text()
                    raise_content_service_error(
                        service="spellchecker_service",
                        operation="fetch_content",
                        message=f"Content not found: {storage_id}",
                        correlation_id=correlation_id,
                        content_service_url=self.content_service_url,
                        status_code=response.status,
                        storage_id=storage_id,
                        response_text=error_text[:200],
                    )

                else:
                    error_text = await response.text()
                    raise_content_service_error(
                        service="spellchecker_service",
                        operation="fetch_content",
                        message=f"Content Service error: {response.status} - {error_text[:100]}",
                        correlation_id=correlation_id,
                        content_service_url=self.content_service_url,
                        status_code=response.status,
                        storage_id=storage_id,
                        response_text=error_text[:200],
                    )

        except aiohttp.ServerTimeoutError:
            raise_content_service_error(
                service="spellchecker_service",
                operation="fetch_content",
                message=f"Timeout fetching content from {storage_id}",
                correlation_id=correlation_id,
                content_service_url=self.content_service_url,
                storage_id=storage_id,
                timeout_seconds=10,
            )

        except aiohttp.ClientError as e:
            raise_content_service_error(
                service="spellchecker_service",
                operation="fetch_content",
                message=f"Connection error fetching content: {str(e)}",
                correlation_id=correlation_id,
                content_service_url=self.content_service_url,
                storage_id=storage_id,
                client_error_type=type(e).__name__,
            )

        except Exception as e:
            logger.error(
                f"{log_prefix}Unexpected error fetching content {storage_id}: {e}",
                exc_info=True,
                extra={"correlation_id": str(correlation_id), "storage_id": storage_id},
            )
            raise_content_service_error(
                service="spellchecker_service",
                operation="fetch_content",
                message=f"Unexpected error fetching content: {str(e)}",
                correlation_id=correlation_id,
                content_service_url=self.content_service_url,
                storage_id=storage_id,
                error_type=type(e).__name__,
            )
