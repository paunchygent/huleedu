"""Content client implementation for the CJ Assessment Service.

This module provides the concrete implementation of ContentClientProtocol,
enabling the CJ service to fetch spellchecked essay content from the Content Service.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import aiohttp
from huleedu_service_libs.logging_utils import create_service_logger

from common_core.error_enums import ErrorCode
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.exceptions import ContentServiceError, map_status_to_error_code
from services.cj_assessment_service.models_api import ErrorDetail
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

    async def fetch_content(
        self, storage_id: str, correlation_id: UUID
    ) -> tuple[str | None, ErrorDetail | None]:
        """Fetch essay text content by storage ID from Content Service.

        Args:
            storage_id: The storage reference ID for the essay text
            correlation_id: Request correlation ID for tracing

        Returns:
            Tuple of (content, error) where only one should be set
        """
        logger.info(
            "Fetching content from Content Service",
            extra={
                "correlation_id": str(correlation_id),
                "storage_id": storage_id,
                "content_service_url": self.content_service_base_url,
            },
        )

        async def _make_content_request() -> tuple[str | None, ErrorDetail | None]:
            """Inner function for retry mechanism."""
            endpoint = f"{self.content_service_base_url}/{storage_id}"
            timeout_config = aiohttp.ClientTimeout(total=self.settings.LLM_REQUEST_TIMEOUT_SECONDS)

            try:
                async with self.session.get(endpoint, timeout=timeout_config) as response:
                    if response.status == 200:
                        content = await response.text()
                        if not content.strip():
                            error_detail = ErrorDetail(
                                error_code=ErrorCode.INVALID_RESPONSE,
                                message="Empty content received from Content Service",
                                correlation_id=correlation_id,
                                timestamp=datetime.now(UTC),
                                details={"storage_id": storage_id},
                            )
                            logger.error(
                                "Empty content received from Content Service",
                                extra={
                                    "error_code": error_detail.error_code.value,
                                    "correlation_id": str(correlation_id),
                                    "storage_id": storage_id,
                                },
                            )
                            return None, error_detail

                        logger.info(
                            "Successfully fetched content from Content Service",
                            extra={
                                "correlation_id": str(correlation_id),
                                "storage_id": storage_id,
                                "content_length": len(content),
                            },
                        )
                        return content, None

                    elif response.status == 404:
                        error_detail = ErrorDetail(
                            error_code=ErrorCode.RESOURCE_NOT_FOUND,
                            message="Content not found in Content Service",
                            correlation_id=correlation_id,
                            timestamp=datetime.now(UTC),
                            details={"storage_id": storage_id},
                        )
                        logger.error(
                            "Content not found in Content Service",
                            extra={
                                "error_code": error_detail.error_code.value,
                                "correlation_id": str(correlation_id),
                                "storage_id": storage_id,
                                "status_code": response.status,
                            },
                        )
                        return None, error_detail

                    else:
                        # Handle other HTTP error responses
                        error_text = await response.text()
                        error_code = map_status_to_error_code(response.status)
                        is_retryable = response.status in [429, 500, 502, 503, 504]

                        error_detail = ErrorDetail(
                            error_code=error_code,
                            message=f"Content Service error: HTTP {response.status}",
                            correlation_id=correlation_id,
                            timestamp=datetime.now(UTC),
                            details={
                                "storage_id": storage_id,
                                "status_code": response.status,
                                "error_text": error_text[:500],  # Truncate long error messages
                                "is_retryable": is_retryable,
                            },
                        )
                        logger.error(
                            "Content Service HTTP error",
                            extra={
                                "error_code": error_detail.error_code.value,
                                "correlation_id": str(correlation_id),
                                "storage_id": storage_id,
                                "status_code": response.status,
                                "is_retryable": is_retryable,
                            },
                        )

                        if is_retryable:
                            raise ContentServiceError(
                                message=f"Content Service error: HTTP {response.status}",
                                correlation_id=correlation_id,
                                status_code=response.status,
                                storage_id=storage_id,
                                is_retryable=True,
                            )

                        return None, error_detail

            except (TimeoutError, aiohttp.ServerTimeoutError):
                error_detail = ErrorDetail(
                    error_code=ErrorCode.TIMEOUT,
                    message="Timeout fetching content from Content Service",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    details={
                        "storage_id": storage_id,
                        "timeout_seconds": self.settings.LLM_REQUEST_TIMEOUT_SECONDS,
                    },
                )
                logger.error(
                    "Timeout fetching content from Content Service",
                    extra={
                        "error_code": error_detail.error_code.value,
                        "correlation_id": str(correlation_id),
                        "storage_id": storage_id,
                        "timeout_seconds": self.settings.LLM_REQUEST_TIMEOUT_SECONDS,
                    },
                )
                # Timeout is retryable
                raise ContentServiceError(
                    message="Timeout fetching content from Content Service",
                    correlation_id=correlation_id,
                    storage_id=storage_id,
                    is_retryable=True,
                )

            except aiohttp.ClientError as e:
                error_detail = ErrorDetail(
                    error_code=ErrorCode.CONNECTION_ERROR,
                    message=f"Content Service connection error: {str(e)}",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    details={"storage_id": storage_id, "exception_type": type(e).__name__},
                )
                logger.error(
                    "Content Service connection error",
                    extra={
                        "error_code": error_detail.error_code.value,
                        "correlation_id": str(correlation_id),
                        "storage_id": storage_id,
                        "exception_type": type(e).__name__,
                    },
                )
                # Connection errors are retryable
                raise ContentServiceError(
                    message=f"Content Service connection error: {str(e)}",
                    correlation_id=correlation_id,
                    storage_id=storage_id,
                    is_retryable=True,
                )

            except Exception as e:
                error_detail = ErrorDetail(
                    error_code=ErrorCode.CONTENT_SERVICE_ERROR,
                    message=f"Unexpected error fetching content: {str(e)}",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    details={"storage_id": storage_id, "exception_type": type(e).__name__},
                )
                logger.error(
                    "Unexpected error fetching content from Content Service",
                    extra={
                        "error_code": error_detail.error_code.value,
                        "correlation_id": str(correlation_id),
                        "storage_id": storage_id,
                        "exception_type": type(e).__name__,
                    },
                )
                return None, error_detail

        # Use retry manager for retryable errors
        try:
            return await self.retry_manager.with_retry(
                _make_content_request, service_name="content_service"
            )
        except ContentServiceError as e:
            # Convert to ErrorDetail for final return
            error_detail = ErrorDetail(
                error_code=ErrorCode.CONTENT_SERVICE_ERROR,
                message=e.message,
                correlation_id=correlation_id,
                timestamp=datetime.now(UTC),
                details=e.details,
            )
            return None, error_detail
