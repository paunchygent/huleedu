"""Content client implementation for the CJ Assessment Service.

This module provides the concrete implementation of ContentClientProtocol,
enabling the CJ service to fetch spellchecked essay content from the Content Service.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import aiohttp
from huleedu_service_libs.error_handling import (
    raise_external_service_error,
    raise_invalid_response,
    raise_resource_not_found,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.protocols import ContentClientProtocol, RetryManagerProtocol

logger = create_service_logger("cj_assessment_service.content_client")


class ContentClientImpl(ContentClientProtocol):
    """Implementation of ContentClientProtocol for fetching essay content."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        settings: Settings,
        retry_manager: RetryManagerProtocol,
    ) -> None:
        """Initialize the content client with HTTP session, settings, and retry manager."""
        self.session = session
        self.settings = settings
        self.retry_manager = retry_manager
        self.content_service_base_url = settings.CONTENT_SERVICE_URL.rstrip("/")

    async def fetch_content(self, storage_id: str, correlation_id: UUID) -> str:
        """Fetch essay text content by storage ID from Content Service.

        Args:
            storage_id: The storage reference ID for the essay text
            correlation_id: Request correlation ID for tracing

        Returns:
            The essay text content

        Raises:
            HuleEduError: On any failure to fetch content
        """
        logger.info(
            "Fetching content from Content Service",
            extra={
                "correlation_id": str(correlation_id),
                "storage_id": storage_id,
                "content_service_url": self.content_service_base_url,
            },
        )

        async def _make_content_request() -> str:
            """Inner function for retry mechanism."""
            endpoint = f"{self.content_service_base_url}/{storage_id}"
            timeout_config = aiohttp.ClientTimeout(total=self.settings.LLM_REQUEST_TIMEOUT_SECONDS)

            async with self.session.get(endpoint, timeout=timeout_config) as response:
                if response.status == 200:
                    content = await response.text()
                    if not content.strip():
                        raise_invalid_response(
                            service="cj_assessment_service",
                            operation="fetch_content",
                            message="Empty content received from Content Service",
                            correlation_id=correlation_id,
                            storage_id=storage_id,
                        )

                    logger.info(
                        "Successfully fetched content from Content Service",
                        extra={
                            "correlation_id": str(correlation_id),
                            "storage_id": storage_id,
                            "content_length": len(content),
                        },
                    )
                    return content

                elif response.status == 404:
                    raise_resource_not_found(
                        service="cj_assessment_service",
                        operation="fetch_content",
                        resource_type="Content",
                        resource_id=storage_id,
                        correlation_id=correlation_id,
                    )

                else:
                    # Handle other HTTP error responses
                    error_text = await response.text()
                    raise_external_service_error(
                        service="cj_assessment_service",
                        operation="fetch_content",
                        external_service="content_service",
                        message=f"Content Service error: HTTP {response.status}",
                        correlation_id=correlation_id,
                        status_code=response.status,
                        error_text=error_text[:500],  # Truncate long error messages
                        storage_id=storage_id,
                    )

        # Use retry manager which will handle TimeoutError, ClientError, etc.
        return await self.retry_manager.with_retry(
            _make_content_request, provider_name="content_service", correlation_id=correlation_id
        )

    async def store_content(self, content: str, content_type: str = "text/plain") -> dict[str, str]:
        """Store content in Content Service.

        Args:
            content: The text content to store
            content_type: MIME type of content

        Returns:
            Dict with 'content_id' key containing the storage ID
        """

        async def _make_store_request() -> dict[str, str]:
            """Make the HTTP request to store content."""
            url = f"{self.content_service_base_url}/store"

            async with self.session.post(
                url,
                json={"content": content, "content_type": content_type},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    content_id = result.get("content_id", "")
                    logger.debug(
                        "Successfully stored content in Content Service",
                        extra={
                            "content_id": content_id,
                            "content_length": len(content),
                        },
                    )
                    return {"content_id": str(content_id)}
                else:
                    error_text = await response.text()
                    raise_external_service_error(
                        service="cj_assessment_service",
                        operation="store_content",
                        external_service="content_service",
                        message=f"Content Service error: HTTP {response.status}",
                        correlation_id=uuid4(),  # Generate new UUID for error tracking
                        status_code=response.status,
                        error_text=error_text[:500],
                    )

        return await self.retry_manager.with_retry(
            _make_store_request, provider_name="content_service", correlation_id=None
        )
