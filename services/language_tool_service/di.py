"""Dependency injection configuration for Language Tool Service using Dishka."""

from __future__ import annotations

from typing import Any

from dishka import Provider, Scope, provide
from huleedu_service_libs.error_handling.correlation import (
    CorrelationContext,
    extract_correlation_context_from_request,
)
from prometheus_client import REGISTRY, CollectorRegistry
from quart import g, request

from services.language_tool_service.config import Settings, settings
from services.language_tool_service.implementations.stub_wrapper import (
    StubLanguageToolWrapper,
)
from services.language_tool_service.metrics import METRICS
from services.language_tool_service.protocols import LanguageToolWrapperProtocol


class CoreInfrastructureProvider(Provider):
    """Provider for core infrastructure dependencies (settings, metrics, correlation context)."""

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide service settings."""
        return settings

    @provide(scope=Scope.APP)
    def provide_metrics_registry(self) -> CollectorRegistry:
        """Provide the global Prometheus metrics registry shared across collectors."""
        return REGISTRY

    @provide(scope=Scope.APP)
    def provide_metrics(self) -> dict[str, Any]:
        """Provide shared Prometheus metrics dictionary."""
        return METRICS

    @provide(scope=Scope.REQUEST)
    def provide_correlation_context(self) -> CorrelationContext:
        """
        Provide correlation context from request headers or query parameters.

        This follows Rule 043.2 for correlation context integration.
        """
        # Check if correlation context already exists in g (set by middleware)
        ctx = getattr(g, "correlation_context", None)
        if isinstance(ctx, CorrelationContext):
            return ctx

        # Fallback to extracting from request directly
        return extract_correlation_context_from_request(request)


class ServiceImplementationsProvider(Provider):
    """Provider for service implementation dependencies."""

    @provide(scope=Scope.APP)
    def provide_language_tool_wrapper(
        self,
        settings: Settings,
    ) -> LanguageToolWrapperProtocol:
        """Provide Language Tool wrapper implementation."""
        return StubLanguageToolWrapper(settings)
