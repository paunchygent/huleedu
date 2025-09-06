"""
Behavioral tests for entitlements API endpoints following Rule 075 standards.

Tests the credit checking, consumption, and balance query endpoints:
- POST /check-credits
- POST /consume-credits
- GET /balance/{user_id}

These tests focus on behavioral testing of HTTP responses and API contract
validation, not internal business logic which is tested in other unit tests.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.error_enums import ErrorCode
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling import HuleEduError, create_test_error_detail
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

# Removed unused import - app instance will be created in test fixture
from services.entitlements_service.protocols import (
    CreditBalanceInfo,
    CreditCheckResponse,
    CreditConsumptionResult,
    CreditManagerProtocol,
)


class TestEntitlementsRoutes:
    """Behavioral tests for entitlements API endpoints."""

    @pytest.fixture
    def mock_credit_manager(self) -> AsyncMock:
        """Create mock credit manager following Rule 075 protocol-based mocking."""
        return AsyncMock(spec=CreditManagerProtocol)

    @pytest.fixture
    async def app_client(
        self,
        mock_credit_manager: AsyncMock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        """
        Return Quart test client with mocked dependencies using Dishka DI.

        Creates fresh app instance to avoid conflicts with existing DI setup,
        similar to file_service testing pattern.
        """
        from quart import Quart

        from services.entitlements_service.api.entitlements_routes import entitlements_bp

        # Define test-specific provider with mocked dependencies
        class TestProvider(Provider):
            @provide(scope=Scope.REQUEST)
            def provide_credit_manager(self) -> CreditManagerProtocol:
                return mock_credit_manager

        # Create fresh test app like CJ Assessment service
        test_app = Quart(__name__)
        test_app.config.update({"TESTING": True})

        # Add error handlers like production app
        from huleedu_service_libs.error_handling.quart import create_error_response
        from pydantic import ValidationError

        @test_app.errorhandler(HuleEduError)
        async def handle_huleedu_error(error: HuleEduError) -> Any:
            return create_error_response(error.error_detail)

        @test_app.errorhandler(ValidationError)
        async def handle_validation_error(error: ValidationError) -> Any:
            return {
                "error": "validation_error",
                "message": "Invalid request data",
                "details": error.errors(),
                "service": "entitlements_service",
            }, 422

        # Create container and configure app for testing
        container = make_async_container(TestProvider())
        QuartDishka(app=test_app, container=container)

        # Register blueprint with same prefix as production
        test_app.register_blueprint(entitlements_bp, url_prefix="/v1/entitlements")

        async with test_app.test_client() as client:
            yield client

        await container.close()

    # POST /check-credits endpoint tests

    @pytest.mark.parametrize(
        "user_id, org_id, metric, amount, allowed, available_credits, expected_source",
        [
            # Basic successful check scenarios
            ("user-123", None, "essay_review", 1, True, 50, "user"),
            ("user-456", "org-789", "batch_process", 5, True, 100, "org"),
            # Swedish character handling in user/org IDs and metrics
            ("användare-åäö", None, "grammatik_kontroll", 1, True, 25, "user"),
            ("lärare-örebro", "skola-malmö", "språk_bedömning", 3, True, 75, "org"),
            # Insufficient credit scenarios
            ("user-no-credits", None, "expensive_op", 10, False, 5, "user"),
            ("user-789", "org-empty", "bulk_analysis", 20, False, 0, "org"),
            # Edge cases - zero and high amounts
            ("user-zero", None, "free_check", 0, True, 100, "user"),
            ("user-bulk", "org-premium", "mass_process", 1000, True, 5000, "org"),
        ],
    )
    async def test_check_credits_success_scenarios(
        self,
        app_client: QuartTestClient,
        mock_credit_manager: AsyncMock,
        user_id: str,
        org_id: str | None,
        metric: str,
        amount: int,
        allowed: bool,
        available_credits: int,
        expected_source: str,
    ) -> None:
        """Test successful credit check scenarios with Swedish characters."""
        # Configure mock response
        check_response = CreditCheckResponse(
            allowed=allowed,
            reason=None if allowed else "Insufficient credits",
            required_credits=amount,
            available_credits=available_credits,
            source=expected_source,
        )
        mock_credit_manager.check_credits.return_value = check_response

        # Prepare request payload
        request_data = {
            "user_id": user_id,
            "metric": metric,
            "amount": amount,
        }
        if org_id is not None:
            request_data["org_id"] = org_id

        # Execute request
        response = await app_client.post("/v1/entitlements/check-credits", json=request_data)

        # Verify response behavior
        assert response.status_code == 200
        data = await response.get_json()
        assert data["allowed"] == allowed
        assert data["required_credits"] == amount
        assert data["available_credits"] == available_credits
        assert data["source"] == expected_source
        if not allowed:
            assert data["reason"] == "Insufficient credits"

        # Verify credit manager was called with correct parameters
        mock_credit_manager.check_credits.assert_called_once_with(
            user_id=user_id,
            org_id=org_id,
            metric=metric,
            amount=amount,
        )

    @pytest.mark.parametrize(
        "request_data",
        [
            # Missing required fields (empty dict should trigger missing body error)
            ({"user_id": "test"}),  # Missing metric should be caught by Pydantic
            ({"metric": "test"}),  # Missing user_id should be caught by Pydantic
            # Invalid field types
            ({"user_id": 123, "metric": "test"}),  # Invalid user_id type
            ({"user_id": "test", "metric": 456}),  # Invalid metric type
            ({"user_id": "test", "metric": "test", "amount": "invalid"}),
        ],
    )
    async def test_check_credits_validation_errors(
        self,
        app_client: QuartTestClient,
        mock_credit_manager: AsyncMock,
        request_data: dict,
    ) -> None:
        """Test request validation for check-credits endpoint."""
        response = await app_client.post("/v1/entitlements/check-credits", json=request_data)

        # Should return 422 for validation errors
        assert response.status_code == 422

        # Verify credit manager was not called for invalid requests
        mock_credit_manager.check_credits.assert_not_called()

    async def test_check_credits_missing_request_body(
        self,
        app_client: QuartTestClient,
        mock_credit_manager: AsyncMock,
    ) -> None:
        """Test check-credits endpoint with missing request body."""
        response = await app_client.post("/v1/entitlements/check-credits")

        # Should return 400 for missing body (handled by raise_validation_error)
        assert response.status_code == 400
        mock_credit_manager.check_credits.assert_not_called()

    async def test_check_credits_service_error(
        self,
        app_client: QuartTestClient,
        mock_credit_manager: AsyncMock,
    ) -> None:
        """Test check-credits endpoint when credit manager raises error."""
        # Configure mock to raise service error
        mock_credit_manager.check_credits.side_effect = HuleEduError(
            error_detail=create_test_error_detail(
                error_code=ErrorCode.PROCESSING_ERROR,
                message="Database connection failed",
                service="entitlements_service",
                operation="check_credits",
            )
        )

        request_data = {
            "user_id": "test-user",
            "metric": "test_metric",
            "amount": 1,
        }

        response = await app_client.post("/v1/entitlements/check-credits", json=request_data)

        # Should return 500 for service errors
        assert response.status_code == 500

    # POST /consume-credits endpoint tests

    @pytest.mark.parametrize(
        "user_id, org_id, metric, amount, success, new_balance, consumed_from",
        [
            # Successful consumption scenarios
            ("user-123", None, "essay_review", 1, True, 49, "user"),
            ("user-456", "org-789", "batch_process", 5, True, 95, "org"),
            # Swedish characters in IDs and metrics
            ("användare-åäö", None, "grammatik_kontroll", 2, True, 23, "user"),
            ("lärare-göteborg", "universitet-stockholm", "språk_bedömning", 3, True, 47, "org"),
            # Failed consumption scenarios
            ("user-insufficient", None, "expensive_op", 10, False, 5, "none"),
            ("user-empty", "org-broke", "premium_feature", 1, False, 0, "none"),
            # Edge cases
            ("user-bulk", "org-enterprise", "mass_operation", 100, True, 4900, "org"),
        ],
    )
    async def test_consume_credits_scenarios(
        self,
        app_client: QuartTestClient,
        mock_credit_manager: AsyncMock,
        user_id: str,
        org_id: str | None,
        metric: str,
        amount: int,
        success: bool,
        new_balance: int,
        consumed_from: str,
    ) -> None:
        """Test credit consumption scenarios with Swedish characters."""
        # Configure mock response
        consumption_result = CreditConsumptionResult(
            success=success,
            new_balance=new_balance,
            consumed_from=consumed_from,
        )
        mock_credit_manager.consume_credits.return_value = consumption_result

        # Prepare request payload
        correlation_id = str(uuid4())
        request_data = {
            "user_id": user_id,
            "metric": metric,
            "amount": amount,
            "correlation_id": correlation_id,
        }
        if org_id is not None:
            request_data["org_id"] = org_id

        # Execute request
        response = await app_client.post("/v1/entitlements/consume-credits", json=request_data)

        # Verify response behavior
        assert response.status_code == 200
        data = await response.get_json()
        assert data["success"] == success
        assert data["new_balance"] == new_balance
        assert data["consumed_from"] == consumed_from

        # Verify credit manager was called correctly
        mock_credit_manager.consume_credits.assert_called_once_with(
            user_id=user_id,
            org_id=org_id,
            metric=metric,
            amount=amount,
            batch_id=None,
            correlation_id=correlation_id,
        )

    async def test_consume_credits_with_batch_id(
        self,
        app_client: QuartTestClient,
        mock_credit_manager: AsyncMock,
    ) -> None:
        """Test credit consumption with batch_id parameter."""
        consumption_result = CreditConsumptionResult(
            success=True,
            new_balance=75,
            consumed_from="org",
        )
        mock_credit_manager.consume_credits.return_value = consumption_result

        batch_id = str(uuid4())
        correlation_id = str(uuid4())
        request_data = {
            "user_id": "batch-user",
            "org_id": "batch-org",
            "metric": "batch_processing",
            "amount": 25,
            "batch_id": batch_id,
            "correlation_id": correlation_id,
        }

        response = await app_client.post("/v1/entitlements/consume-credits", json=request_data)

        assert response.status_code == 200
        mock_credit_manager.consume_credits.assert_called_once_with(
            user_id="batch-user",
            org_id="batch-org",
            metric="batch_processing",
            amount=25,
            batch_id=batch_id,
            correlation_id=correlation_id,
        )

    async def test_consume_credits_missing_correlation_id(
        self,
        app_client: QuartTestClient,
        mock_credit_manager: AsyncMock,
    ) -> None:
        """Test consume-credits endpoint requires correlation_id."""
        request_data = {
            "user_id": "test-user",
            "metric": "test_metric",
            "amount": 1,
            # Missing required correlation_id
        }

        response = await app_client.post("/v1/entitlements/consume-credits", json=request_data)

        # Should return 422 for Pydantic validation error
        assert response.status_code == 422
        mock_credit_manager.consume_credits.assert_not_called()

    # GET /balance/{user_id} endpoint tests

    @pytest.mark.parametrize(
        "user_id, user_balance, org_balance, org_id",
        [
            # Basic balance scenarios
            ("user-123", 50, None, None),
            ("user-456", 25, 100, "org-789"),
            # Swedish character handling in user IDs
            ("användare-åäö", 75, None, None),
            ("lärare-örebro", 30, 200, "skola-malmö"),
            ("student-göteborg", 10, 500, "universitet-stockholm"),
            # Edge cases - zero balances
            ("user-empty", 0, None, None),
            ("user-org-empty", 15, 0, "org-broke"),
            # High balance scenarios
            ("user-premium", 9999, 50000, "enterprise-org"),
        ],
    )
    async def test_get_balance_scenarios(
        self,
        app_client: QuartTestClient,
        mock_credit_manager: AsyncMock,
        user_id: str,
        user_balance: int,
        org_balance: int | None,
        org_id: str | None,
    ) -> None:
        """Test balance retrieval with Swedish character user IDs."""
        # Configure mock response
        balance_info = CreditBalanceInfo(
            user_balance=user_balance,
            org_balance=org_balance,
            org_id=org_id,
        )
        mock_credit_manager.get_balance.return_value = balance_info

        # Execute request
        response = await app_client.get(f"/v1/entitlements/balance/{user_id}")

        # Verify response behavior
        assert response.status_code == 200
        data = await response.get_json()
        assert data["user_balance"] == user_balance
        assert data["org_balance"] == org_balance
        assert data["org_id"] == org_id

        # Verify credit manager was called correctly
        mock_credit_manager.get_balance.assert_called_once_with(
            user_id=user_id,
            org_id=None,  # TODO: Currently hardcoded, will be from user context
        )

    async def test_get_balance_url_encoding(
        self,
        app_client: QuartTestClient,
        mock_credit_manager: AsyncMock,
    ) -> None:
        """Test balance endpoint with URL-encoded Swedish characters."""
        balance_info = CreditBalanceInfo(
            user_balance=42,
            org_balance=None,
            org_id=None,
        )
        mock_credit_manager.get_balance.return_value = balance_info

        # URL-encoded Swedish characters
        encoded_user_id = "l%C3%A4rare-%C3%B6rebro"  # lärare-örebro
        response = await app_client.get(f"/v1/entitlements/balance/{encoded_user_id}")

        assert response.status_code == 200
        # Verify that URL decoding worked and original Swedish ID was passed
        mock_credit_manager.get_balance.assert_called_once_with(
            user_id="lärare-örebro",
            org_id=None,
        )

    async def test_get_balance_service_error(
        self,
        app_client: QuartTestClient,
        mock_credit_manager: AsyncMock,
    ) -> None:
        """Test balance endpoint when credit manager raises error."""
        # Configure mock to raise service error
        mock_credit_manager.get_balance.side_effect = HuleEduError(
            error_detail=create_test_error_detail(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message="User not found",
                service="entitlements_service",
                operation="get_balance",
            )
        )

        response = await app_client.get("/v1/entitlements/balance/nonexistent-user")

        # Should return 404 for not found errors
        assert response.status_code == 404

    async def test_get_balance_empty_user_id(
        self,
        app_client: QuartTestClient,
        mock_credit_manager: AsyncMock,
    ) -> None:
        """Test balance endpoint with empty user_id parameter."""
        # Empty string in URL path should be handled by Quart routing
        response = await app_client.get("/v1/entitlements/balance/")

        # Should return 404 for malformed route
        assert response.status_code == 404
        mock_credit_manager.get_balance.assert_not_called()
