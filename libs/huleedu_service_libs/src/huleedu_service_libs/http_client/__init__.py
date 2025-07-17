"""Shared HTTP client utilities for HuleEdu services.

This module provides standardized HTTP client functionality that eliminates
duplication across services while maintaining protocol-based architecture
and structured error handling patterns.

Key Components:
- BaseHttpClient: Core HTTP client with standardized error handling
- ContentServiceClient: Content Service specific operations
- HTTP protocols: Type-safe interfaces for all HTTP operations
- Configuration: Pydantic models for HTTP client settings
- DI providers: Dishka integration for dependency injection

Usage:
    from huleedu_service_libs.http_client import (
        HttpClientProtocol,
        ContentServiceClientProtocol,
        BaseHttpClient,
        ContentServiceClient,
        HttpClientConfig,
        ContentServiceConfig,
        HttpClientProvider
    )
"""

from .base_client import BaseHttpClient
from .config import ContentServiceConfig, HttpClientConfig
from .content_service_client import ContentServiceClient
from .di_providers import ContentServiceClientProvider, HttpClientProvider
from .protocols import ContentServiceClientProtocol, HttpClientProtocol

__all__ = [
    "HttpClientProtocol",
    "ContentServiceClientProtocol",
    "HttpClientConfig",
    "ContentServiceConfig",
    "BaseHttpClient",
    "ContentServiceClient",
    "HttpClientProvider",
    "ContentServiceClientProvider",
]
