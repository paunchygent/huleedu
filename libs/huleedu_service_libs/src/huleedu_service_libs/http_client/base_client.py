"""Base HTTP client implementation with standardized error handling.

This module provides the core HTTP client implementation that eliminates
duplication across services while maintaining structured error handling
and observability patterns.
"""

import json
from typing import Any
from uuid import UUID

import aiohttp

from huleedu_service_libs.logging_utils import create_service_logger

from .config import HttpClientConfig
from .error_mapping import map_aiohttp_error_to_huleedu_error
from .protocols import HttpClientProtocol

logger = create_service_logger("huleedu_service_libs.http_client.base_client")


class BaseHttpClient(HttpClientProtocol):
    """Base HTTP client with standardized error handling and logging.

    This client provides the foundational HTTP operations that all services
    need, with consistent error handling, correlation ID tracking, and
    structured logging following HuleEdu patterns.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        service_name: str,
        config: HttpClientConfig,
    ):
        """Initialize the HTTP client.

        Args:
            session: aiohttp ClientSession for making requests
            service_name: Name of the service using this client
            config: Configuration for HTTP client behavior
        """
        self.session = session
        self.service_name = service_name
        self.config = config

    async def get(
        self,
        url: str,
        correlation_id: UUID,
        timeout_seconds: int | None = None,
        headers: dict[str, str] | None = None,
        **context: Any,
    ) -> str:
        """Execute GET request with structured error handling.

        Args:
            url: Target URL for the GET request
            correlation_id: Request correlation ID for tracing
            timeout_seconds: Request timeout in seconds (uses config default if None)
            headers: Optional HTTP headers
            **context: Additional context for error reporting

        Returns:
            Response body as string

        Raises:
            HuleEduError: On any HTTP error, timeout, or connection issue
        """
        effective_timeout = timeout_seconds or self.config.default_timeout_seconds

        logger.debug(
            f"HTTP GET to {url}",
            extra={
                "correlation_id": str(correlation_id),
                "url": url,
                "timeout_seconds": effective_timeout,
                "service": self.service_name,
                **context,
            },
        )

        try:
            timeout = aiohttp.ClientTimeout(total=effective_timeout)
            async with self.session.get(url, timeout=timeout, headers=headers) as response:
                response.raise_for_status()
                content: str = await response.text()

                logger.debug(
                    f"HTTP GET successful: {len(content)} chars",
                    extra={
                        "correlation_id": str(correlation_id),
                        "url": url,
                        "status": response.status,
                        "content_length": len(content),
                        "service": self.service_name,
                    },
                )
                return content

        except Exception as e:
            # Map aiohttp error to structured HuleEdu error
            map_aiohttp_error_to_huleedu_error(
                error=e,
                service=self.service_name,
                operation="http_get",
                correlation_id=correlation_id,
                url=url,
                timeout_seconds=effective_timeout,
                **context,
            )

    async def post(
        self,
        url: str,
        data: bytes | str,
        correlation_id: UUID,
        timeout_seconds: int | None = None,
        headers: dict[str, str] | None = None,
        **context: Any,
    ) -> dict[str, Any]:
        """Execute POST request with structured error handling.

        Args:
            url: Target URL for the POST request
            data: Request body data (bytes or string)
            correlation_id: Request correlation ID for tracing
            timeout_seconds: Request timeout in seconds (uses config default if None)
            headers: Optional HTTP headers
            **context: Additional context for error reporting

        Returns:
            Response body parsed as JSON dict

        Raises:
            HuleEduError: On any HTTP error, timeout, or connection issue
        """
        effective_timeout = timeout_seconds or self.config.default_timeout_seconds
        data_length = len(data) if isinstance(data, (str, bytes)) else 0

        logger.debug(
            f"HTTP POST to {url} with {data_length} bytes",
            extra={
                "correlation_id": str(correlation_id),
                "url": url,
                "timeout_seconds": effective_timeout,
                "data_length": data_length,
                "service": self.service_name,
                **context,
            },
        )

        try:
            timeout = aiohttp.ClientTimeout(total=effective_timeout)

            # Prepare data payload
            if isinstance(data, str):
                payload = data.encode("utf-8")
            else:
                payload = data

            async with self.session.post(
                url, data=payload, timeout=timeout, headers=headers
            ) as response:
                response.raise_for_status()

                # Parse JSON response
                try:
                    result: dict[str, Any] = await response.json()

                    logger.debug(
                        f"HTTP POST successful: {response.status}",
                        extra={
                            "correlation_id": str(correlation_id),
                            "url": url,
                            "status": response.status,
                            "response_keys": list(result.keys())
                            if isinstance(result, dict)
                            else [],
                            "service": self.service_name,
                        },
                    )

                    return result

                except json.JSONDecodeError as json_error:
                    # Handle invalid JSON response
                    response_text = await response.text()
                    logger.error(
                        f"Invalid JSON response from {url}: {json_error}",
                        extra={
                            "correlation_id": str(correlation_id),
                            "url": url,
                            "status": response.status,
                            "response_preview": response_text[:200],
                            "service": self.service_name,
                        },
                    )

                    # Use error mapping to create structured error
                    map_aiohttp_error_to_huleedu_error(
                        error=json_error,
                        service=self.service_name,
                        operation="http_post_json_parse",
                        correlation_id=correlation_id,
                        url=url,
                        timeout_seconds=effective_timeout,
                        json_error=str(json_error),
                        response_preview=response_text[:200],
                        **context,
                    )

        except Exception as e:
            # Map aiohttp error to structured HuleEdu error
            map_aiohttp_error_to_huleedu_error(
                error=e,
                service=self.service_name,
                operation="http_post",
                correlation_id=correlation_id,
                url=url,
                timeout_seconds=effective_timeout,
                data_length=data_length,
                **context,
            )
