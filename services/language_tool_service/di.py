"""Dependency injection configuration for Language Tool Service using Dishka."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from dishka import Provider, Scope, provide
from huleedu_service_libs.error_handling.correlation import (
    CorrelationContext,
    extract_correlation_context_from_request,
)
from prometheus_client import REGISTRY, CollectorRegistry
from quart import g, request

from services.language_tool_service.config import Settings, settings
from services.language_tool_service.implementations.language_tool_manager import (
    LanguageToolManager,
)
from services.language_tool_service.implementations.language_tool_wrapper import (
    LanguageToolWrapper,
)
from services.language_tool_service.implementations.stub_wrapper import (
    StubLanguageToolWrapper,
)
from services.language_tool_service.metrics import METRICS
from services.language_tool_service.protocols import (
    LanguageToolManagerProtocol,
    LanguageToolWrapperProtocol,
)


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
    async def provide_language_tool_manager(
        self,
        settings: Settings,
    ) -> AsyncIterator[LanguageToolManager]:
        """Provide Language Tool process manager with lifecycle management."""
        # Check if we should use the stub implementation
        use_stub = os.getenv("USE_STUB_LANGUAGE_TOOL", "false").lower() == "true"

        if use_stub:
            # Return a dummy manager for stub mode
            manager = LanguageToolManager(settings)
            yield manager
        else:
            # Check if JAR exists before starting
            jar_path = Path(settings.LANGUAGE_TOOL_JAR_PATH)
            if not jar_path.exists():
                # If JAR doesn't exist, fall back to stub mode
                from huleedu_service_libs.logging_utils import create_service_logger

                logger = create_service_logger("language_tool_service.di")
                logger.warning(
                    f"LanguageTool JAR not found at {jar_path}, using stub implementation"
                )
                manager = LanguageToolManager(settings)
                yield manager
            else:
                # Production mode: start and manage the server
                manager = LanguageToolManager(settings)
                await manager.start()
                try:
                    yield manager
                finally:
                    await manager.stop()

    @provide(scope=Scope.APP)
    def provide_language_tool_wrapper(
        self,
        settings: Settings,
        manager: LanguageToolManager,
        metrics: dict[str, Any],
    ) -> LanguageToolWrapperProtocol:
        """Provide Language Tool wrapper implementation."""
        # Check if we should use the stub implementation
        use_stub = os.getenv("USE_STUB_LANGUAGE_TOOL", "false").lower() == "true"

        if use_stub:
            # Use stub implementation for development/testing
            return StubLanguageToolWrapper(settings)

        # Check if JAR exists
        jar_path = Path(settings.LANGUAGE_TOOL_JAR_PATH)
        if not jar_path.exists():
            # Fall back to stub if JAR is not available
            return StubLanguageToolWrapper(settings)

        # Use production implementation with metrics
        return LanguageToolWrapper(settings, manager, metrics)

    @provide(scope=Scope.APP)
    def provide_language_tool_manager_protocol(
        self, manager: LanguageToolManager
    ) -> LanguageToolManagerProtocol:
        """Provide Language Tool manager as protocol interface."""
        return manager
