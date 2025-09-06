"""Structural tests for DI providers (no internal patching).

Validates provider scopes, required factory methods, and container basics.
Split from the previous monolithic test_di_setup.py per Rule 075.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from dishka import Provider, Scope, make_async_container
from huleedu_service_libs.outbox import OutboxProvider
from sqlalchemy.ext.asyncio import AsyncEngine

from services.entitlements_service.di import (
    CoreProvider,
    EntitlementsServiceProvider,
    ImplementationProvider,
    ServiceProvider,
)


class TestDIProviderStructure:
    def test_core_provider_has_app_scope(self) -> None:
        provider = CoreProvider()
        assert provider.scope == Scope.APP

    def test_implementation_provider_has_request_scope(self) -> None:
        provider = ImplementationProvider()
        assert provider.scope == Scope.REQUEST

    def test_service_provider_has_request_scope(self) -> None:
        provider = ServiceProvider()
        assert provider.scope == Scope.REQUEST

    def test_entitlements_provider_has_app_scope(self) -> None:
        mock_engine = AsyncMock(spec=AsyncEngine)
        provider = EntitlementsServiceProvider(engine=mock_engine)
        assert provider.scope == Scope.APP

    @pytest.mark.parametrize(
        "provider_class,expected_methods",
        [
            (
                CoreProvider,
                {
                    "provide_settings",
                    "provide_service_name",
                    "provide_metrics_registry",
                    "provide_database_metrics",
                    "provide_circuit_breaker_registry",
                    "provide_redis_client",
                    "provide_kafka_publisher",
                    "provide_session_factory",
                },
            ),
            (
                ImplementationProvider,
                {
                    "provide_repository",
                    "provide_policy_loader",
                    "provide_rate_limiter",
                    "provide_outbox_manager",
                    "provide_event_publisher",
                },
            ),
            (
                ServiceProvider,
                {
                    "provide_credit_manager",
                },
            ),
            (
                EntitlementsServiceProvider,
                {
                    "provide_engine",
                },
            ),
        ],
    )
    def test_provider_has_required_factory_methods(
        self,
        provider_class: type[Provider],
        expected_methods: set[str],
    ) -> None:
        if provider_class == EntitlementsServiceProvider:
            mock_engine = AsyncMock(spec=AsyncEngine)
            provider = provider_class(engine=mock_engine)  # type: ignore[call-arg]
        else:
            provider = provider_class()

        provider_methods = set(dir(provider))
        assert expected_methods.issubset(provider_methods)


class TestDIContainerBasics:
    def test_container_creation_with_all_providers_succeeds(self) -> None:
        mock_engine = AsyncMock(spec=AsyncEngine)

        container = make_async_container(
            CoreProvider(),
            ImplementationProvider(),
            ServiceProvider(),
            EntitlementsServiceProvider(engine=mock_engine),
            OutboxProvider(),
        )
        assert container is not None

    def test_multiple_containers_are_isolated(self) -> None:
        mock_engine = AsyncMock(spec=AsyncEngine)
        c1 = make_async_container(
            CoreProvider(),
            ImplementationProvider(),
            ServiceProvider(),
            EntitlementsServiceProvider(engine=mock_engine),
            OutboxProvider(),
        )
        c2 = make_async_container(
            CoreProvider(),
            ImplementationProvider(),
            ServiceProvider(),
            EntitlementsServiceProvider(engine=mock_engine),
            OutboxProvider(),
        )

        assert c1 is not c2

    def test_entitlements_provider_requires_engine_parameter(self) -> None:
        with pytest.raises(TypeError):
            EntitlementsServiceProvider()  # type: ignore[call-arg]

    def test_provider_scope_configuration_is_consistent(self) -> None:
        mock_engine = AsyncMock(spec=AsyncEngine)
        core = CoreProvider()
        ents = EntitlementsServiceProvider(engine=mock_engine)
        impl = ImplementationProvider()
        svc = ServiceProvider()

        assert core.scope == Scope.APP
        assert ents.scope == Scope.APP
        assert impl.scope == Scope.REQUEST
        assert svc.scope == Scope.REQUEST
