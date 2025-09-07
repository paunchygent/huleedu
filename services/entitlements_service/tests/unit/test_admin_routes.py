"""
Behavioral tests for Entitlements admin endpoints with DI-mocked dependencies.

Validates:
- POST /v1/admin/credits/set (user/org) happy path
- Error transparency with correlation threading on failures
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.error_handling.quart import register_error_handlers
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.entitlements_service.protocols import (
    CreditManagerProtocol,
    EntitlementsRepositoryProtocol,
)
from huleedu_service_libs.error_handling.correlation import (
    CorrelationContext,
    extract_correlation_context_from_request,
)


class TestAdminRoutes:
    @pytest.fixture
    def mock_credit_manager(self) -> AsyncMock:
        return AsyncMock(spec=CreditManagerProtocol)

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        return AsyncMock(spec=EntitlementsRepositoryProtocol)

    @pytest.fixture
    async def app_client(
        self,
        mock_credit_manager: AsyncMock,
        mock_repository: AsyncMock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        from quart import Quart

        from services.entitlements_service.api.admin_routes import admin_bp

        class TestProvider(Provider):
            @provide(scope=Scope.REQUEST)
            def provide_credit_manager(self) -> CreditManagerProtocol:
                return mock_credit_manager

            @provide(scope=Scope.REQUEST)
            def provide_repository(self) -> EntitlementsRepositoryProtocol:
                return mock_repository

            @provide(scope=Scope.REQUEST)
            def provide_correlation_context(self) -> CorrelationContext:
                # Build from incoming request for route injection
                from quart import request

                return extract_correlation_context_from_request(request)

        app = Quart(__name__)
        app.config.update({"TESTING": True})

        # Register standard error handlers for structured responses
        register_error_handlers(app)

        container = make_async_container(TestProvider())
        QuartDishka(app=app, container=container)
        app.register_blueprint(admin_bp, url_prefix="/v1/admin")

        async with app.test_client() as client:
            yield client

        await container.close()

    @pytest.mark.asyncio
    async def test_set_credits_success_user(
        self,
        app_client: QuartTestClient,
        mock_repository: AsyncMock,
        mock_credit_manager: AsyncMock,
    ) -> None:
        # Arrange
        mock_repository.get_credit_balance.return_value = 0
        mock_credit_manager.adjust_balance.return_value = 100000

        payload = {
            "subject_type": "user",
            "subject_id": "test-user-1",
            "balance": 100000,
        }

        # Act
        resp = await app_client.post(
            "/v1/admin/credits/set",
            json=payload,
            headers={"X-Correlation-ID": "11111111-1111-1111-1111-111111111111"},
        )

        # Assert
        assert resp.status_code == 200
        data = await resp.get_json()
        assert data["success"] is True
        assert data["balance"] == 100000
        assert data["subject_type"] == "user"
        assert data["subject_id"] == "test-user-1"
        mock_repository.get_credit_balance.assert_called_once_with("user", "test-user-1")
        mock_credit_manager.adjust_balance.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_credits_processing_error_exposes_details(
        self,
        app_client: QuartTestClient,
        mock_repository: AsyncMock,
        mock_credit_manager: AsyncMock,
    ) -> None:
        # Arrange
        mock_repository.get_credit_balance.return_value = 0
        mock_credit_manager.adjust_balance.side_effect = Exception("DB error")

        payload = {
            "subject_type": "org",
            "subject_id": "org-åäö",
            "balance": 500,
        }
        corr = "22222222-2222-2222-2222-222222222222"

        # Act
        resp = await app_client.post(
            "/v1/admin/credits/set",
            json=payload,
            headers={"X-Correlation-ID": corr},
        )

        # Assert
        assert resp.status_code == 500
        body = await resp.get_json()
        assert "error" in body
        err = body["error"]
        # Correlation should be threaded back
        assert err.get("correlation_id") is not None
        # Details should contain subject identifiers for transparency
        details = err.get("details", {})
        assert details.get("subject_type") == "org"
        assert details.get("subject_id") == "org-åäö"
