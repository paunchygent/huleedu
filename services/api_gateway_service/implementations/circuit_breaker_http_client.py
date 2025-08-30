"""Circuit breaker HTTP client for API Gateway service.

This module provides a circuit breaker wrapper for the API Gateway's HTTP client,
maintaining compatibility with the service's specific HttpClientProtocol.
"""

from __future__ import annotations

import httpx

from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker
from services.api_gateway_service.protocols import HttpClientProtocol


class ApiGatewayCircuitBreakerHttpClient(HttpClientProtocol):
    """HTTP client with circuit breaker protection for API Gateway.

    This wrapper implements the API Gateway's HttpClientProtocol and adds
    circuit breaker protection to HTTP operations while preserving the
    service's specific interface (returning raw httpx.Response objects).
    """

    def __init__(self, delegate: HttpClientProtocol, circuit_breaker: CircuitBreaker) -> None:
        """Initialize circuit breaker HTTP client.

        Args:
            delegate: The actual HTTP client implementation
            circuit_breaker: Circuit breaker for resilience protection
        """
        self._delegate = delegate
        self._circuit_breaker = circuit_breaker

    async def post(
        self,
        url: str,
        *,
        data: dict | None = None,
        files: list | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> httpx.Response:
        """Send POST request with circuit breaker protection.

        Args:
            url: Target URL for the POST request
            data: Form data dictionary (optional)
            files: List of files to upload (optional)
            headers: Additional HTTP headers (optional)
            timeout: Request timeout (optional)

        Returns:
            Raw httpx Response object

        Raises:
            CircuitBreakerError: If circuit is open
            httpx.HTTPError: On HTTP errors (when circuit is closed)
        """
        return await self._circuit_breaker.call(
            self._delegate.post,
            url,
            data=data,
            files=files,
            headers=headers,
            timeout=timeout,
        )

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> httpx.Response:
        """Send GET request with circuit breaker protection.

        Args:
            url: Target URL for the GET request
            headers: Additional HTTP headers (optional)
            timeout: Request timeout (optional)

        Returns:
            Raw httpx Response object

        Raises:
            CircuitBreakerError: If circuit is open
            httpx.HTTPError: On HTTP errors (when circuit is closed)
        """
        return await self._circuit_breaker.call(
            self._delegate.get,
            url,
            headers=headers,
            timeout=timeout,
        )
