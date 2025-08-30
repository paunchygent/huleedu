"""Circuit breaker HTTP client wrapper.

This module provides a typed wrapper for HTTP clients that adds circuit breaker
protection while maintaining full protocol compatibility.
"""

from typing import Any
from uuid import UUID

from huleedu_service_libs.http_client.protocols import HttpClientProtocol
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker

logger = create_service_logger("circuit_breaker_http_client")


class CircuitBreakerHttpClient(HttpClientProtocol):
    """HTTP client with circuit breaker protection.

    This wrapper implements HttpClientProtocol and adds circuit breaker
    protection to all HTTP operations. It delegates all actual HTTP work
    to the underlying client while providing resilience through the
    circuit breaker pattern.

    Circuit Breaker Behavior:
    - CLOSED: All requests pass through normally
    - OPEN: Requests are blocked and CircuitBreakerError is raised
    - HALF_OPEN: Limited requests allowed to test recovery
    """

    def __init__(self, delegate: HttpClientProtocol, circuit_breaker: CircuitBreaker) -> None:
        """Initialize circuit breaker HTTP client.

        Args:
            delegate: The actual HTTP client implementation
            circuit_breaker: Circuit breaker for resilience protection
        """
        self._delegate = delegate
        self._circuit_breaker = circuit_breaker

    async def get(
        self,
        url: str,
        correlation_id: UUID,
        timeout_seconds: int = 10,
        headers: dict[str, str] | None = None,
        **context: Any,
    ) -> str:
        """Execute GET request with circuit breaker protection.

        Args:
            url: Target URL for the GET request
            correlation_id: Request correlation ID for tracing
            timeout_seconds: Request timeout in seconds
            headers: Optional HTTP headers
            **context: Additional context for error reporting

        Returns:
            Response body as string

        Raises:
            CircuitBreakerError: If circuit is open
            HuleEduError: On any HTTP error, timeout, or connection issue
        """
        logger.debug(
            f"GET {url} through circuit breaker", extra={"correlation_id": str(correlation_id)}
        )
        return await self._circuit_breaker.call(
            self._delegate.get, url, correlation_id, timeout_seconds, headers, **context
        )

    async def post(
        self,
        url: str,
        data: bytes | str,
        correlation_id: UUID,
        timeout_seconds: int = 10,
        headers: dict[str, str] | None = None,
        **context: Any,
    ) -> dict[str, Any]:
        """Execute POST request with circuit breaker protection.

        Args:
            url: Target URL for the POST request
            data: Request body data (bytes or string)
            correlation_id: Request correlation ID for tracing
            timeout_seconds: Request timeout in seconds
            headers: Optional HTTP headers
            **context: Additional context for error reporting

        Returns:
            Response body parsed as JSON dict

        Raises:
            CircuitBreakerError: If circuit is open
            HuleEduError: On any HTTP error, timeout, or connection issue
        """
        logger.debug(
            f"POST {url} through circuit breaker", extra={"correlation_id": str(correlation_id)}
        )
        return await self._circuit_breaker.call(
            self._delegate.post, url, data, correlation_id, timeout_seconds, headers, **context
        )
