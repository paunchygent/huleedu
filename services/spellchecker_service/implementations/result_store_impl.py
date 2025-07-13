"""Default implementation of ResultStoreProtocol."""

from __future__ import annotations

from uuid import UUID

import aiohttp
from huleedu_service_libs.error_handling import raise_content_service_error
from huleedu_service_libs.logging_utils import create_service_logger

# OpenTelemetry tracing handled by HuleEduError automatically
from common_core.domain_enums import ContentType
from services.spellchecker_service.protocols import ResultStoreProtocol

logger = create_service_logger("spellchecker_service.result_store_impl")


class DefaultResultStore(ResultStoreProtocol):
    """Default implementation of ResultStoreProtocol with structured error handling."""

    def __init__(self, content_service_url: str):
        self.content_service_url = content_service_url

    async def store_content(
        self,
        original_storage_id: str,
        content_type: ContentType,
        content: str,
        http_session: aiohttp.ClientSession,
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> str:
        """Store content to Content Service with structured error handling.

        Args:
            original_storage_id: Original content storage ID for reference
            content_type: Type of content being stored
            content: Content string to store
            http_session: HTTP client session
            correlation_id: Request correlation ID for tracing
            essay_id: Optional essay ID for logging context

        Returns:
            New storage ID for the stored content

        Raises:
            HuleEduError: On any failure to store content
        """
        log_prefix = f"Essay {essay_id}: " if essay_id else ""

        logger.debug(
            f"{log_prefix}Storing content (type: {content_type.value}, length: {len(content)}) "
            f"to Content Service via {self.content_service_url}",
            extra={"correlation_id": str(correlation_id), "content_type": content_type.value},
        )

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with http_session.post(
                self.content_service_url,
                data=content.encode("utf-8"),
                timeout=timeout,
            ) as response:
                # Use response.raise_for_status() to handle all 2xx codes correctly
                response.raise_for_status()
                # Parse response JSON - only reached on successful 2xx response
                try:
                    data: dict[str, str] = await response.json()
                    storage_id = data.get("storage_id")

                    if not storage_id:
                        raise_content_service_error(
                            service="spellchecker_service",
                            operation="store_content",
                            message="Content service response missing 'storage_id' field",
                            correlation_id=correlation_id,
                            content_service_url=self.content_service_url,
                            status_code=response.status,
                            content_type=content_type.value,
                            response_data=str(data),
                        )

                    logger.info(
                        f"{log_prefix}Successfully stored content, new storage_id: {storage_id}",
                        extra={"correlation_id": str(correlation_id), "storage_id": storage_id},
                    )
                    return storage_id

                except Exception as json_error:
                    response_text = await response.text()
                    raise_content_service_error(
                        service="spellchecker_service",
                        operation="store_content",
                        message=f"Failed to parse Content Service JSON response: {str(json_error)}",
                        correlation_id=correlation_id,
                        content_service_url=self.content_service_url,
                        status_code=response.status,
                        content_type=content_type.value,
                        response_text=response_text[:200],
                        json_error=str(json_error),
                    )

        except aiohttp.ClientResponseError as e:
            # Handle HTTP errors (4xx/5xx) from raise_for_status()
            # Note: response body is not available in ClientResponseError
            raise_content_service_error(
                service="spellchecker_service",
                operation="store_content",
                message=f"Content Service HTTP error: {e.status} - {e.message}",
                correlation_id=correlation_id,
                content_service_url=self.content_service_url,
                status_code=e.status,
                content_type=content_type.value,
                response_text=e.message[:200] if e.message else "No error message",
            )

        except aiohttp.ServerTimeoutError:
            raise_content_service_error(
                service="spellchecker_service",
                operation="store_content",
                message="Timeout storing content to Content Service",
                correlation_id=correlation_id,
                content_service_url=self.content_service_url,
                content_type=content_type.value,
                content_length=len(content),
                timeout_seconds=10,
            )

        except aiohttp.ClientError as e:
            raise_content_service_error(
                service="spellchecker_service",
                operation="store_content",
                message=f"Connection error storing content: {str(e)}",
                correlation_id=correlation_id,
                content_service_url=self.content_service_url,
                content_type=content_type.value,
                content_length=len(content),
                client_error_type=type(e).__name__,
            )

        except Exception as e:
            logger.error(
                f"{log_prefix}Unexpected error storing content: {e}",
                exc_info=True,
                extra={"correlation_id": str(correlation_id), "content_type": content_type.value},
            )
            raise_content_service_error(
                service="spellchecker_service",
                operation="store_content",
                message=f"Unexpected error storing content: {str(e)}",
                correlation_id=correlation_id,
                content_service_url=self.content_service_url,
                content_type=content_type.value,
                content_length=len(content),
                error_type=type(e).__name__,
            )
