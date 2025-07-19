"""
Protocols for API Gateway Service.

Defines all interfaces used for dependency injection following DDD principles.
Business logic depends on these protocols, not concrete implementations.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

import httpx
from fastapi import Request
from prometheus_client import Counter, Histogram


class HttpClientProtocol(Protocol):
    """Protocol for HTTP client dependencies."""

    async def post(
        self,
        url: str,
        *,
        data: dict | None = None,
        files: list | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> httpx.Response:
        """Send POST request with form data and files."""
        ...

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> httpx.Response:
        """Send GET request."""
        ...


class MetricsProtocol(Protocol):
    """Protocol for metrics collection matching GatewayMetrics exactly."""

    @property
    def http_requests_total(self) -> Counter:
        """Total HTTP requests counter."""
        ...

    @property
    def http_request_duration_seconds(self) -> Histogram:
        """HTTP request duration histogram."""
        ...

    @property
    def events_published_total(self) -> Counter:
        """Events published counter."""
        ...

    @property
    def downstream_service_calls_total(self) -> Counter:
        """Downstream service calls counter."""
        ...

    @property
    def downstream_service_call_duration_seconds(self) -> Histogram:
        """Downstream service call duration histogram."""
        ...

    @property
    def api_errors_total(self) -> Counter:
        """API errors counter."""
        ...


class AuthenticationProtocol(Protocol):
    """Protocol for authentication and authorization operations."""

    async def extract_user_id(self, request: Request) -> str:
        """Extract and validate user ID from request."""
        ...

    async def extract_correlation_id(self, request: Request) -> UUID:
        """Extract or generate correlation ID from request."""
        ...

    async def validate_bearer_token(self, request: Request) -> str:
        """Validate bearer token and return the token."""
        ...
