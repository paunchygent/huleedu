"""
Behavioral tests for bulk credit check endpoint.

Covers:
- POST /check-credits/bulk happy path and denial paths
- Swedish character handling and org-first attribution
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling import HuleEduError, create_test_error_detail
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.entitlements_service.protocols import (
    BulkCreditCheckResult,
    CreditManagerProtocol,
    PerMetricCreditStatus,
)


class TestEntitlementsBulkRoute:
    @pytest.fixture
    def mock_credit_manager(self) -> AsyncMock:
        return AsyncMock(spec=CreditManagerProtocol)

    @pytest.fixture
    async def app_client(
        self,
        mock_credit_manager: AsyncMock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        from quart import Quart

        from services.entitlements_service.api.entitlements_routes import entitlements_bp

        class TestProvider(Provider):
            @provide(scope=Scope.REQUEST)
            def provide_credit_manager(self) -> CreditManagerProtocol:
                return mock_credit_manager

        app = Quart(__name__)
        app.config.update({"TESTING": True})

        from huleedu_service_libs.error_handling.quart import create_error_response
        from pydantic import ValidationError

        @app.errorhandler(HuleEduError)
        async def handle_huleedu_error(error: HuleEduError) -> Any:
            return create_error_response(error.error_detail)

        @app.errorhandler(ValidationError)
        async def handle_validation_error(error: ValidationError) -> Any:
            return {
                "error": "validation_error",
                "message": "Invalid request data",
                "details": error.errors(),
                "service": "entitlements_service",
            }, 422

        container = make_async_container(TestProvider())
        QuartDishka(app=app, container=container)

        app.register_blueprint(entitlements_bp, url_prefix="/v1/entitlements")

        async with app.test_client() as client:
            yield client

        await container.close()

    async def test_bulk_allowed_org_first_with_swedish_ids(
        self, app_client: QuartTestClient, mock_credit_manager: AsyncMock
    ) -> None:
        per_metric = {
            "cj_comparison": PerMetricCreditStatus(
                required=10, available=1000, allowed=True, source="org"
            ),
            "ai_feedback_generation": PerMetricCreditStatus(
                required=50, available=1000, allowed=True, source="org"
            ),
        }
        result = BulkCreditCheckResult(
            allowed=True,
            required_credits=60,
            available_credits=1000,
            per_metric=per_metric,
            denial_reason=None,
            correlation_id=str(uuid4()),
        )
        mock_credit_manager.check_credits_bulk.return_value = result

        payload = {
            "user_id": "lärare-örebro",
            "org_id": "skola-malmö",
            "requirements": {"cj_comparison": 10, "ai_feedback_generation": 10},
            "correlation_id": str(uuid4()),
        }
        resp = await app_client.post("/v1/entitlements/check-credits/bulk", json=payload)
        assert resp.status_code == 200
        data = await resp.get_json()
        assert data["allowed"] is True
        assert data["required_credits"] == 60
        assert data["available_credits"] == 1000
        assert data["per_metric"]["cj_comparison"]["allowed"] is True
        assert data["per_metric"]["ai_feedback_generation"]["source"] == "org"

        mock_credit_manager.check_credits_bulk.assert_called_once()

    async def test_bulk_denied_insufficient_with_breakdown(
        self, app_client: QuartTestClient, mock_credit_manager: AsyncMock
    ) -> None:
        per_metric = {
            "cj_comparison": PerMetricCreditStatus(
                required=200, available=50, allowed=False, source=None, reason="insufficient_credits"
            ),
            "ai_feedback_generation": PerMetricCreditStatus(
                required=50, available=50, allowed=False, source=None, reason="insufficient_credits"
            ),
        }
        result = BulkCreditCheckResult(
            allowed=False,
            required_credits=250,
            available_credits=50,
            per_metric=per_metric,
            denial_reason="insufficient_credits",
            correlation_id=str(uuid4()),
        )
        mock_credit_manager.check_credits_bulk.return_value = result

        payload = {
            "user_id": "user-1",
            "requirements": {"cj_comparison": 200, "ai_feedback_generation": 10},
        }
        resp = await app_client.post("/v1/entitlements/check-credits/bulk", json=payload)
        assert resp.status_code == 402
        data = await resp.get_json()
        assert data["allowed"] is False
        assert data["denial_reason"] == "insufficient_credits"
        assert data["required_credits"] == 250

    async def test_bulk_rate_limited_returns_429(
        self, app_client: QuartTestClient, mock_credit_manager: AsyncMock
    ) -> None:
        per_metric = {
            "cj_comparison": PerMetricCreditStatus(
                required=10, available=0, allowed=False, source=None, reason="rate_limit_exceeded"
            ),
            "ai_feedback_generation": PerMetricCreditStatus(
                required=10, available=0, allowed=True, source=None
            ),
        }
        result = BulkCreditCheckResult(
            allowed=False,
            required_credits=20,
            available_credits=0,
            per_metric=per_metric,
            denial_reason="rate_limit_exceeded",
            correlation_id=str(uuid4()),
        )
        mock_credit_manager.check_credits_bulk.return_value = result

        payload = {
            "user_id": "user-rl",
            "requirements": {"cj_comparison": 10, "ai_feedback_generation": 10},
        }
        resp = await app_client.post("/v1/entitlements/check-credits/bulk", json=payload)
        assert resp.status_code == 429
        data = await resp.get_json()
        assert data["denial_reason"] == "rate_limit_exceeded"

    @pytest.mark.parametrize(
        "payload",
        [
            {},  # missing body handled by 400
            {"user_id": "x"},  # missing requirements -> 422 by Pydantic
            {"requirements": {"cj_comparison": 1}},  # missing user_id -> 422
            {"user_id": "x", "requirements": []},  # wrong type -> 422
        ],
    )
    async def test_bulk_validation_errors(
        self, app_client: QuartTestClient, mock_credit_manager: AsyncMock, payload: dict[str, Any]
    ) -> None:
        resp = await app_client.post("/v1/entitlements/check-credits/bulk", json=payload)
        if payload == {}:
            assert resp.status_code == 400
        else:
            assert resp.status_code == 422
        mock_credit_manager.check_credits_bulk.assert_not_called()

