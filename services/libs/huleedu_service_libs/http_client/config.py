"""Configuration models for HTTP client utilities.

This module provides Pydantic models for configuring HTTP client behavior,
following HuleEdu's configuration management patterns.
"""

from pydantic import BaseModel, Field


class HttpClientConfig(BaseModel):
    """Configuration for HTTP client behavior and resilience patterns.

    This model defines the core HTTP client settings that control
    timeouts, retry behavior, and connection management.
    """

    default_timeout_seconds: int = Field(
        default=10, description="Default timeout for HTTP requests in seconds", ge=1, le=300
    )

    max_retries: int = Field(
        default=3, description="Maximum number of retry attempts for failed requests", ge=0, le=10
    )

    retry_base_delay: float = Field(
        default=1.0, description="Base delay between retry attempts in seconds", ge=0.1, le=60.0
    )

    retry_max_delay: float = Field(
        default=30.0,
        description="Maximum delay between retry attempts in seconds",
        ge=1.0,
        le=300.0,
    )

    retry_exponential_base: float = Field(
        default=2.0, description="Exponential backoff base multiplier", ge=1.0, le=10.0
    )

    connection_pool_size: int = Field(
        default=20, description="Maximum number of concurrent connections", ge=1, le=1000
    )

    enable_keepalive: bool = Field(default=True, description="Enable HTTP connection keep-alive")


class ContentServiceConfig(BaseModel):
    """Configuration for Content Service HTTP client.

    This model defines the settings specific to Content Service
    interactions, including endpoints and service-specific timeouts.
    """

    base_url: str = Field(
        description="Base URL for Content Service (e.g., http://content-service:8001)"
    )

    fetch_endpoint_path: str = Field(
        default="",
        description="Additional path for content fetch endpoint (appended to base_url/{storage_id})",
    )

    store_endpoint_path: str = Field(
        default="", description="Additional path for content store endpoint (appended to base_url)"
    )

    http_config: HttpClientConfig = Field(
        default_factory=HttpClientConfig,
        description="HTTP client configuration for Content Service requests",
    )

    def get_fetch_url(self, storage_id: str) -> str:
        """Build the complete URL for fetching content by storage ID.

        Args:
            storage_id: Content storage identifier

        Returns:
            Complete URL for content fetch operation
        """
        base = self.base_url.rstrip("/")
        path = self.fetch_endpoint_path.strip("/")

        if path:
            return f"{base}/{path}/{storage_id}"
        else:
            return f"{base}/{storage_id}"

    def get_store_url(self) -> str:
        """Build the complete URL for storing content.

        Returns:
            Complete URL for content store operation
        """
        base = self.base_url.rstrip("/")
        path = self.store_endpoint_path.strip("/")

        if path:
            return f"{base}/{path}"
        else:
            return base
