"""Default implementation of ContentClientProtocol for NLP Service."""

from __future__ import annotations

import asyncio
from uuid import UUID

import aiohttp
from huleedu_service_libs.error_handling import raise_content_service_error
from huleedu_service_libs.logging_utils import create_service_logger

from services.nlp_service.protocols import ContentClientProtocol

logger = create_service_logger("nlp_service.content_client_impl")


class DefaultContentClient(ContentClientProtocol):
    """Default implementation of ContentClientProtocol with structured error handling."""

    def __init__(self, content_service_url: str) -> None:
        """Initialize content client.

        Args:
            content_service_url: Base URL for Content Service
        """
        self.content_service_url = content_service_url

    async def fetch_content(
        self,
        storage_id: str,
        http_session: aiohttp.ClientSession,
        correlation_id: UUID,
    ) -> str:
        """Fetch content from Content Service with structured error handling.

        Args:
            storage_id: Content storage identifier
            http_session: HTTP client session
            correlation_id: Request correlation ID for tracing

        Returns:
            Content as string

        Raises:
            HuleEduError: On any failure to fetch content
        """
        url = f"{self.content_service_url}/{storage_id}"

        logger.debug(
            f"Fetching content from URL: {url}",
            extra={"correlation_id": str(correlation_id), "storage_id": storage_id},
        )

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            logger.debug(
                f"Making HTTP GET request to: {url}",
                extra={"correlation_id": str(correlation_id)},
            )
            async with http_session.get(url, timeout=timeout) as response:
                # Use response.raise_for_status() to handle all 2xx codes correctly
                response.raise_for_status()
                # Parse response - only reached on successful 2xx response
                content = await response.text()
                logger.debug(
                    f"Successfully fetched content from {storage_id} (length: {len(content)})",
                    extra={"correlation_id": str(correlation_id), "storage_id": storage_id},
                )
                return content

        except aiohttp.ClientResponseError as e:
            # Handle HTTP errors (4xx/5xx) from raise_for_status()
            if e.status == 404:
                raise_content_service_error(
                    service="nlp_service",
                    operation="fetch_content",
                    message=f"Content not found: {storage_id}",
                    correlation_id=correlation_id,
                    content_service_url=self.content_service_url,
                    status_code=e.status,
                    storage_id=storage_id,
                )
            else:
                # Note: response body is not available in ClientResponseError
                raise_content_service_error(
                    service="nlp_service",
                    operation="fetch_content",
                    message=f"Content Service HTTP error: {e.status} - {e.message}",
                    correlation_id=correlation_id,
                    content_service_url=self.content_service_url,
                    status_code=e.status,
                    storage_id=storage_id,
                    response_text=e.message[:200] if e.message else "No error message",
                )

        except asyncio.TimeoutError:
            logger.error(
                "HTTP request timed out after 10 seconds",
                extra={"correlation_id": str(correlation_id)},
            )
            raise_content_service_error(
                service="nlp_service",
                operation="fetch_content",
                message=f"Timeout fetching content from {storage_id}",
                correlation_id=correlation_id,
                content_service_url=self.content_service_url,
                storage_id=storage_id,
            )

        except aiohttp.ClientError as e:
            logger.error(
                f"HTTP client error: {e}",
                exc_info=True,
                extra={"correlation_id": str(correlation_id)},
            )
            raise_content_service_error(
                service="nlp_service",
                operation="fetch_content",
                message=f"Client error fetching content: {str(e)}",
                correlation_id=correlation_id,
                content_service_url=self.content_service_url,
                storage_id=storage_id,
                error_type=type(e).__name__,
            )

        except Exception as e:
            logger.error(
                f"Unexpected error fetching content: {e}",
                exc_info=True,
                extra={"correlation_id": str(correlation_id)},
            )
            raise_content_service_error(
                service="nlp_service",
                operation="fetch_content",
                message=f"Unexpected error: {str(e)}",
                correlation_id=correlation_id,
                content_service_url=self.content_service_url,
                storage_id=storage_id,
                error_type=type(e).__name__,
            )
