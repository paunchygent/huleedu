"""Dishka providers for HTTP client utilities.

This module provides dependency injection providers for the shared HTTP
client utilities, following HuleEdu's established DI patterns with Dishka.
"""

from aiohttp import ClientSession
from dishka import Provider, Scope, provide

from .base_client import BaseHttpClient
from .config import ContentServiceConfig, HttpClientConfig
from .content_service_client import ContentServiceClient
from .protocols import ContentServiceClientProtocol, HttpClientProtocol


class HttpClientProvider(Provider):
    """Dishka provider for base HTTP client utilities.

    This provider creates the base HTTP client with standardized error
    handling and logging. Services can use this directly or build
    higher-level clients on top of it.
    """

    @provide(scope=Scope.APP)
    def provide_http_client_config(self) -> HttpClientConfig:
        """Provide default HTTP client configuration.

        Services can override this provider to customize HTTP client behavior
        such as timeouts, retry settings, and connection pooling.

        Returns:
            Default HTTP client configuration
        """
        return HttpClientConfig()

    @provide(scope=Scope.APP)
    def provide_base_http_client(
        self,
        session: ClientSession,
        config: HttpClientConfig,
        service_name: str,
    ) -> HttpClientProtocol:
        """Provide base HTTP client with standardized error handling.

        Args:
            session: aiohttp ClientSession (provided by service)
            config: HTTP client configuration
            service_name: Name of the service using this client (provided by service)

        Returns:
            HTTP client protocol implementation
        """
        return BaseHttpClient(session=session, service_name=service_name, config=config)


class ContentServiceClientProvider(Provider):
    """Dishka provider for Content Service HTTP client.

    This provider creates a Content Service specific client built on top
    of the base HTTP client, with optional circuit breaker protection.
    """

    @provide(scope=Scope.APP)
    def provide_content_service_client(
        self,
        http_client: HttpClientProtocol,
        content_service_config: ContentServiceConfig,
    ) -> ContentServiceClientProtocol:
        """Provide base Content Service client.

        Args:
            http_client: Base HTTP client for making requests
            content_service_config: Configuration for Content Service operations

        Returns:
            Content Service client protocol implementation

        Note:
            Services should wrap this with CircuitBreakerContentServiceClient
            in their own DI if circuit breaker protection is needed.
        """
        return ContentServiceClient(http_client=http_client, config=content_service_config)


class ContentServiceConfigProvider(Provider):
    """Dishka provider for Content Service configuration.

    This is a helper provider that services can inherit from or use
    to provide Content Service configuration from their settings.
    Services should override provide_content_service_config to inject
    their specific settings.
    """

    @provide(scope=Scope.APP)
    def provide_content_service_config(self) -> ContentServiceConfig:
        """Provide Content Service configuration.

        This is a placeholder implementation that services should override
        to provide their specific Content Service URL and configuration.

        Example:
            @provide(scope=Scope.APP)
            def provide_content_service_config(self, settings: Settings) -> ContentServiceConfig:
                return ContentServiceConfig(
                    base_url=settings.CONTENT_SERVICE_URL,
                    http_config=HttpClientConfig(default_timeout_seconds=15)
                )

        Returns:
            Content Service configuration

        Raises:
            NotImplementedError: Services must override this method
        """
        raise NotImplementedError(
            "Services must override provide_content_service_config to provide "
            "their specific Content Service URL and configuration"
        )


class ServiceNameProvider(Provider):
    """Dishka provider for service name.

    This is a helper provider that services should use to provide
    their service name for HTTP client logging and error reporting.
    """

    @provide(scope=Scope.APP)
    def provide_service_name(self) -> str:
        """Provide service name for HTTP client.

        This is a placeholder implementation that services should override
        to provide their specific service name.

        Example:
            @provide(scope=Scope.APP)
            def provide_service_name(self) -> str:
                return "spellchecker_service"

        Returns:
            Service name string

        Raises:
            NotImplementedError: Services must override this method
        """
        raise NotImplementedError(
            "Services must override provide_service_name to provide "
            "their specific service name for HTTP client logging"
        )
