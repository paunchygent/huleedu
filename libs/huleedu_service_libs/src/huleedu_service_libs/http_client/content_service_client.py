"""Content Service specific HTTP client implementation.

This module provides Content Service specific operations built on top of
the base HTTP client, with proper error handling and response parsing
for Content Service API endpoints.
"""

from typing import cast
from uuid import UUID

from common_core.domain_enums import ContentType

from huleedu_service_libs.error_handling import raise_invalid_response
from huleedu_service_libs.logging_utils import create_service_logger

from .config import ContentServiceConfig
from .protocols import ContentServiceClientProtocol, HttpClientProtocol

logger = create_service_logger("huleedu_service_libs.http_client.content_service_client")


class ContentServiceClient(ContentServiceClientProtocol):
    """Content Service specific HTTP client implementation.

    This client provides high-level operations for interacting with the
    Content Service, built on top of the base HTTP client for consistent
    error handling and observability.
    """

    def __init__(
        self,
        http_client: HttpClientProtocol,
        config: ContentServiceConfig,
    ):
        """Initialize the Content Service client.

        Args:
            http_client: Base HTTP client for making requests
            config: Configuration for Content Service operations
        """
        self.http_client = http_client
        self.config = config

    async def fetch_content(
        self,
        storage_id: str,
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> str:
        """Fetch content by storage ID from Content Service.

        Args:
            storage_id: Content storage identifier
            correlation_id: Request correlation ID for tracing
            essay_id: Optional essay ID for logging context

        Returns:
            Content text

        Raises:
            HuleEduError: On fetch failure, content not found, or service error
        """
        url = self.config.get_fetch_url(storage_id)

        # Build context for error reporting and logging
        context = {"storage_id": storage_id, "external_service": "content_service"}
        if essay_id:
            context["essay_id"] = essay_id

        log_prefix = f"Essay {essay_id}: " if essay_id else ""
        logger.debug(
            f"{log_prefix}Fetching content {storage_id} from Content Service",
            extra={"correlation_id": str(correlation_id), "storage_id": storage_id, "url": url},
        )

        content = await self.http_client.get(
            url=url,
            correlation_id=correlation_id,
            timeout_seconds=self.config.http_config.default_timeout_seconds,
            headers=None,
            **context,
        )

        logger.debug(
            f"{log_prefix}Successfully fetched content {storage_id} ({len(content)} chars)",
            extra={
                "correlation_id": str(correlation_id),
                "storage_id": storage_id,
                "content_length": len(content),
            },
        )

        return content

    async def store_content(
        self,
        content: str,
        content_type: ContentType,
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> str:
        """Store content to Content Service and return storage ID.

        Args:
            content: Content text to store
            content_type: Type of content being stored
            correlation_id: Request correlation ID for tracing
            essay_id: Optional essay ID for logging context

        Returns:
            New storage ID for the stored content

        Raises:
            HuleEduError: On storage failure or invalid response
        """
        url = self.config.get_store_url()

        # Build context for error reporting and logging
        context = {
            "content_type": content_type.value,
            "content_length": len(content),
            "external_service": "content_service",
        }
        if essay_id:
            context["essay_id"] = essay_id

        log_prefix = f"Essay {essay_id}: " if essay_id else ""
        logger.debug(
            f"{log_prefix}Storing content to Content Service "
            f"(type: {content_type.value}, length: {len(content)})",
            extra={
                "correlation_id": str(correlation_id),
                "content_type": content_type.value,
                "content_length": len(content),
                "url": url,
            },
        )

        # Store content via HTTP POST
        result = await self.http_client.post(
            url=url,
            data=content.encode("utf-8"),
            correlation_id=correlation_id,
            timeout_seconds=self.config.http_config.default_timeout_seconds,
            **context,
        )

        # Extract storage_id from response
        storage_id = result.get("storage_id")
        if not storage_id or not isinstance(storage_id, str):
            logger.error(
                f"{log_prefix}Content Service response missing or invalid 'storage_id' field",
                extra={
                    "correlation_id": str(correlation_id),
                    "response_data": str(result),
                    "content_type": content_type.value,
                },
            )

            raise_invalid_response(
                service="content_service_client",
                operation="store_content",
                message="Content Service response missing or invalid 'storage_id' field",
                correlation_id=correlation_id,
                response_data=str(result),
                content_type=content_type.value,
                expected_field="storage_id",
                **context,
            )

        logger.info(
            f"{log_prefix}Successfully stored content, new storage_id: {storage_id}",
            extra={
                "correlation_id": str(correlation_id),
                "storage_id": storage_id,
                "content_type": content_type.value,
            },
        )

        return cast(str, storage_id)
