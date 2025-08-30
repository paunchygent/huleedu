"""HTTP client implementation for API Gateway service.

This module provides an HTTP client implementation that conforms to the
API Gateway's HttpClientProtocol while using httpx for the actual HTTP operations.
"""

from __future__ import annotations

import httpx

from services.api_gateway_service.protocols import HttpClientProtocol


class ApiGatewayHttpClient(HttpClientProtocol):
    """HTTP client implementation for API Gateway.

    This client implements the API Gateway's specific HttpClientProtocol,
    which returns raw httpx.Response objects rather than parsed content.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        """Initialize the HTTP client.

        Args:
            client: The underlying httpx AsyncClient to use
        """
        self._client = client

    async def post(
        self,
        url: str,
        *,
        data: dict | None = None,
        files: list | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> httpx.Response:
        """Send POST request with form data and files.

        Args:
            url: Target URL for the POST request
            data: Form data dictionary (optional)
            files: List of files to upload (optional)
            headers: Additional HTTP headers (optional)
            timeout: Request timeout (optional)

        Returns:
            Raw httpx Response object
        """
        return await self._client.post(
            url=url,
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
        """Send GET request.

        Args:
            url: Target URL for the GET request
            headers: Additional HTTP headers (optional)
            timeout: Request timeout (optional)

        Returns:
            Raw httpx Response object
        """
        return await self._client.get(
            url=url,
            headers=headers,
            timeout=timeout,
        )
