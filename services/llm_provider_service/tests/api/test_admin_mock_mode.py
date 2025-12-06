"""Unit tests for /admin/mock-mode endpoint.

These tests verify that the admin mock-mode endpoint correctly reflects
the Settings-based mock configuration used by the service DI container.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from dishka import Provider, Scope, make_async_container, provide
from quart import Quart
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.llm_provider_service.api.admin_routes import admin_bp
from services.llm_provider_service.config import MockMode, Settings


def _base_settings(**overrides: Any) -> Settings:
    """Create Settings with minimal required fields for admin tests."""
    defaults: dict[str, Any] = {
        "SERVICE_NAME": "llm_provider_service",
        "USE_MOCK_LLM": False,
        "ALLOW_MOCK_PROVIDER": True,
        "MOCK_MODE": MockMode.DEFAULT,
        # Infrastructure fields required by Settings base class
        "REDIS_URL": "redis://localhost:6379/0",
        "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
        # Admin API enabled by default for tests
        "ADMIN_API_ENABLED": True,
    }
    defaults.update(overrides)
    return Settings(**defaults)


class TestAdminMockMode:
    """Tests for /admin/mock-mode endpoint."""

    @pytest.fixture
    async def app_client(self) -> AsyncGenerator[QuartTestClient, None]:
        """Create a Quart test client with injected Settings."""
        test_settings = _base_settings(
            USE_MOCK_LLM=True,
            MOCK_MODE=MockMode.CJ_GENERIC_BATCH,
        )

        class TestProvider(Provider):
            @provide(scope=Scope.APP)
            def provide_settings(self) -> Settings:
                return test_settings

        test_app = Quart(__name__)
        test_app.config.update({"TESTING": True})
        test_app.register_blueprint(admin_bp)

        container = make_async_container(TestProvider())
        QuartDishka(app=test_app, container=container)

        async with test_app.test_client() as client:
            yield client

        await container.close()

    @pytest.mark.asyncio
    async def test_admin_mock_mode_returns_cj_generic_profile(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Endpoint reflects cj_generic_batch profile when configured."""
        response = await app_client.get("/admin/mock-mode")

        assert response.status_code == 200
        data: dict[str, Any] = await response.get_json()

        assert data["use_mock_llm"] is True
        assert data["mock_mode"] == "cj_generic_batch"

    @pytest.mark.asyncio
    async def test_admin_mock_mode_returns_eng5_profiles(
        self,
    ) -> None:
        """Endpoint reflects ENG5 anchor and LOWER5 profiles when configured."""

        async def _assert_mode(mode: MockMode, expected_value: str) -> None:
            test_settings = _base_settings(USE_MOCK_LLM=True, MOCK_MODE=mode)

            class TestProvider(Provider):
                @provide(scope=Scope.APP)
                def provide_settings(self) -> Settings:
                    return test_settings

            test_app = Quart(__name__)
            test_app.config.update({"TESTING": True})
            test_app.register_blueprint(admin_bp)

            container = make_async_container(TestProvider())
            QuartDishka(app=test_app, container=container)

            async with test_app.test_client() as client:
                response = await client.get("/admin/mock-mode")

            await container.close()

            assert response.status_code == 200
            data: dict[str, Any] = await response.get_json()
            assert data["use_mock_llm"] is True
            assert data["mock_mode"] == expected_value

        await _assert_mode(MockMode.ENG5_ANCHOR_GPT51_LOW, "eng5_anchor_gpt51_low")
        await _assert_mode(MockMode.ENG5_LOWER5_GPT51_LOW, "eng5_lower5_gpt51_low")

    @pytest.mark.asyncio
    async def test_admin_mock_mode_returns_null_when_default_mode(self) -> None:
        """Endpoint returns null mock_mode when using DEFAULT profile."""
        test_settings = _base_settings(USE_MOCK_LLM=True, MOCK_MODE=MockMode.DEFAULT)

        class TestProvider(Provider):
            @provide(scope=Scope.APP)
            def provide_settings(self) -> Settings:
                return test_settings

        test_app = Quart(__name__)
        test_app.config.update({"TESTING": True})
        test_app.register_blueprint(admin_bp)

        container = make_async_container(TestProvider())
        QuartDishka(app=test_app, container=container)

        async with test_app.test_client() as client:
            response = await client.get("/admin/mock-mode")

        await container.close()

        assert response.status_code == 200
        data: dict[str, Any] = await response.get_json()

        assert data["use_mock_llm"] is True
        assert data["mock_mode"] is None

    @pytest.mark.asyncio
    async def test_admin_mock_mode_returns_404_when_admin_api_disabled(self) -> None:
        """Endpoint returns 404 when ADMIN_API_ENABLED is False."""
        test_settings = _base_settings(ADMIN_API_ENABLED=False)

        class TestProvider(Provider):
            @provide(scope=Scope.APP)
            def provide_settings(self) -> Settings:
                return test_settings

        test_app = Quart(__name__)
        test_app.config.update({"TESTING": True})
        test_app.register_blueprint(admin_bp)

        container = make_async_container(TestProvider())
        QuartDishka(app=test_app, container=container)

        async with test_app.test_client() as client:
            response = await client.get("/admin/mock-mode")

        await container.close()

        assert response.status_code == 404
