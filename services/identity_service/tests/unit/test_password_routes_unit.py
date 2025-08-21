"""
Unit tests for password management API routes.

Tests password reset and change endpoints: POST /v1/auth/request-password-reset,
POST /v1/auth/reset-password, and POST /v1/auth/change-password following the
established Quart+Dishka testing patterns with proper DI mocking.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, NoReturn
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from dishka import Provider, Scope, make_async_container, provide
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.identity_service.api.schemas import (
    RequestPasswordResetResponse,
    ResetPasswordResponse,
)
from services.identity_service.app import app
from services.identity_service.domain_handlers.password_reset_handler import (
    PasswordResetHandler,
    RequestPasswordResetResult,
    ResetPasswordResult,
)
from services.identity_service.protocols import TokenIssuer


class TestPasswordRoutes:
    """Test password management API endpoints using proper Quart+Dishka patterns."""

    @pytest.fixture
    def mock_password_reset_handler(self) -> AsyncMock:
        """Create mock password reset handler."""
        return AsyncMock(spec=PasswordResetHandler)

    @pytest.fixture
    def mock_token_issuer(self) -> AsyncMock:
        """Create mock token issuer."""
        return AsyncMock(spec=TokenIssuer)

    @pytest.fixture
    async def app_client(
        self,
        mock_password_reset_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        """
        Return a Quart test client configured with mocked dependencies using Dishka.
        This fixture overrides production providers with test providers that supply our mocks.
        """

        # 1. Define a test-specific provider that provides our mocks
        class TestProvider(Provider):
            @provide(scope=Scope.REQUEST)
            def provide_password_reset_handler(self) -> PasswordResetHandler:
                return mock_password_reset_handler

            @provide(scope=Scope.REQUEST)
            def provide_token_issuer(self) -> TokenIssuer:
                return mock_token_issuer

        # 2. Create a new container with our test provider
        container = make_async_container(TestProvider())

        # 3. Apply the container to the app instance for the test
        app.config.update({"TESTING": True})
        QuartDishka(app=app, container=container)

        async with app.test_client() as client:
            yield client

        # 4. Clean up the container after the test
        await container.close()

    async def test_request_password_reset_success(
        self,
        app_client: QuartTestClient,
        mock_password_reset_handler: AsyncMock,
    ) -> None:
        """Test successful password reset request with email non-disclosure security."""
        # Arrange
        email = "user@example.com"
        mock_response = RequestPasswordResetResponse(
            message="If the email address exists, a password reset link will be sent",
            correlation_id="test-correlation-123",
        )
        mock_result = RequestPasswordResetResult(mock_response)
        mock_password_reset_handler.request_password_reset.return_value = mock_result

        # Act
        response = await app_client.post("/v1/auth/request-password-reset", json={"email": email})

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert "If the email address exists" in data["message"]
        assert "correlation_id" in data

        # Verify handler was called with correct parameters
        mock_password_reset_handler.request_password_reset.assert_called_once()
        call_args = mock_password_reset_handler.request_password_reset.call_args
        assert call_args[1]["reset_request"].email == email
        assert call_args[1]["ip_address"] == "<local>"  # Test environment default

    async def test_request_password_reset_swedish_email(
        self,
        app_client: QuartTestClient,
        mock_password_reset_handler: AsyncMock,
    ) -> None:
        """Test password reset request with Swedish characters in email address."""
        # Arrange
        swedish_email = "åsa.öberg@skolan.se"
        mock_response = RequestPasswordResetResponse(
            message="If the email address exists, a password reset link will be sent",
            correlation_id="test-correlation-456",
        )
        mock_result = RequestPasswordResetResult(mock_response)
        mock_password_reset_handler.request_password_reset.return_value = mock_result

        # Act
        response = await app_client.post(
            "/v1/auth/request-password-reset", json={"email": swedish_email}
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert "If the email address exists" in data["message"]

        # Verify Swedish email was handled correctly
        mock_password_reset_handler.request_password_reset.assert_called_once()
        call_args = mock_password_reset_handler.request_password_reset.call_args
        assert call_args[1]["reset_request"].email == swedish_email

    async def test_request_password_reset_invalid_email_format(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test password reset request with malformed email address."""
        # Arrange
        invalid_email = "not-an-email"

        # Act
        response = await app_client.post(
            "/v1/auth/request-password-reset", json={"email": invalid_email}
        )

        # Assert - Pydantic validation error caught by general exception handler
        assert response.status_code == 500

    async def test_request_password_reset_handler_error(
        self,
        app_client: QuartTestClient,
        mock_password_reset_handler: AsyncMock,
    ) -> None:
        """Test password reset request when handler raises HuleEduError."""
        # Arrange
        from huleedu_service_libs.error_handling import raise_validation_error

        def mock_handler_error(**kwargs: Any) -> NoReturn:
            correlation_id = kwargs.get("correlation_id", uuid4())
            raise_validation_error(
                service="identity_service",
                operation="request_password_reset",
                field="email",
                message="Rate limit exceeded",
                correlation_id=correlation_id,
            )

        mock_password_reset_handler.request_password_reset.side_effect = mock_handler_error

        # Act
        response = await app_client.post(
            "/v1/auth/request-password-reset", json={"email": "user@example.com"}
        )

        # Assert
        assert response.status_code == 400
        data = await response.get_json()
        error_detail = data["error"]
        assert "Rate limit exceeded" in error_detail["message"]
        assert error_detail["error_code"] == "VALIDATION_ERROR"

    async def test_reset_password_success(
        self,
        app_client: QuartTestClient,
        mock_password_reset_handler: AsyncMock,
    ) -> None:
        """Test successful password reset with valid token."""
        # Arrange
        reset_token = "valid-reset-token-123"
        new_password = "NewSecurePassword123!"
        mock_response = ResetPasswordResponse(message="Password reset successfully")
        mock_result = ResetPasswordResult(mock_response)
        mock_password_reset_handler.reset_password.return_value = mock_result

        # Act
        response = await app_client.post(
            "/v1/auth/reset-password", json={"token": reset_token, "new_password": new_password}
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["message"] == "Password reset successfully"

        # Verify handler was called with correct parameters
        mock_password_reset_handler.reset_password.assert_called_once()
        call_args = mock_password_reset_handler.reset_password.call_args
        assert call_args[1]["reset_request"].token == reset_token
        assert call_args[1]["reset_request"].new_password == new_password

    async def test_reset_password_invalid_token(
        self,
        app_client: QuartTestClient,
        mock_password_reset_handler: AsyncMock,
    ) -> None:
        """Test password reset with invalid token."""
        # Arrange
        from huleedu_service_libs.error_handling.identity_factories import (
            raise_verification_token_invalid_error,
        )

        def mock_invalid_token(**kwargs: Any) -> NoReturn:
            correlation_id = kwargs.get("correlation_id", uuid4())
            raise_verification_token_invalid_error(
                service="identity_service",
                operation="reset_password",
                correlation_id=correlation_id,
            )

        mock_password_reset_handler.reset_password.side_effect = mock_invalid_token

        # Act
        response = await app_client.post(
            "/v1/auth/reset-password",
            json={"token": "invalid-token", "new_password": "NewPassword123!"},
        )

        # Assert
        assert response.status_code == 400
        data = await response.get_json()
        error_detail = data["error"]
        assert error_detail["error_code"] == "IDENTITY_VERIFICATION_TOKEN_INVALID"

    async def test_reset_password_expired_token(
        self,
        app_client: QuartTestClient,
        mock_password_reset_handler: AsyncMock,
    ) -> None:
        """Test password reset with expired token."""
        # Arrange
        from huleedu_service_libs.error_handling.identity_factories import (
            raise_verification_token_expired_error,
        )

        def mock_expired_token(**kwargs: Any) -> NoReturn:
            correlation_id = kwargs.get("correlation_id", uuid4())
            raise_verification_token_expired_error(
                service="identity_service",
                operation="reset_password",
                correlation_id=correlation_id,
            )

        mock_password_reset_handler.reset_password.side_effect = mock_expired_token

        # Act
        response = await app_client.post(
            "/v1/auth/reset-password",
            json={"token": "expired-token", "new_password": "NewPassword123!"},
        )

        # Assert
        assert response.status_code == 400
        data = await response.get_json()
        error_detail = data["error"]
        assert error_detail["error_code"] == "IDENTITY_VERIFICATION_TOKEN_EXPIRED"

    async def test_change_password_success(
        self,
        app_client: QuartTestClient,
        mock_password_reset_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test successful password change for authenticated user."""
        # Arrange
        user_id = "user-123"
        jwt_token = "valid.jwt.token"
        current_password = "CurrentPassword123!"
        new_password = "NewPassword456!"

        mock_token_issuer.verify.return_value = {"sub": user_id}
        mock_response = ResetPasswordResponse(message="Password changed successfully")
        mock_result = ResetPasswordResult(mock_response)
        mock_password_reset_handler.change_password.return_value = mock_result

        # Act
        response = await app_client.post(
            "/v1/auth/change-password",
            json={"current_password": current_password, "new_password": new_password},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["message"] == "Password changed successfully"

        # Verify token was verified and handler was called
        mock_token_issuer.verify.assert_called_once_with(jwt_token)
        mock_password_reset_handler.change_password.assert_called_once()
        call_args = mock_password_reset_handler.change_password.call_args
        assert call_args[1]["user_id"] == user_id
        assert call_args[1]["current_password"] == current_password
        assert call_args[1]["new_password"] == new_password

    async def test_change_password_no_authorization(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test password change without authorization token."""
        # Act
        response = await app_client.post(
            "/v1/auth/change-password", json={"current_password": "current", "new_password": "new"}
        )

        # Assert
        assert response.status_code == 401
        data = await response.get_json()
        assert data["error"] == "Authorization token required"

    async def test_change_password_invalid_token(
        self,
        app_client: QuartTestClient,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test password change with invalid JWT token."""
        # Arrange
        mock_token_issuer.verify.side_effect = Exception("Invalid token")

        # Act
        response = await app_client.post(
            "/v1/auth/change-password",
            json={"current_password": "current", "new_password": "new"},
            headers={"Authorization": "Bearer invalid.token"},
        )

        # Assert
        assert response.status_code == 401
        data = await response.get_json()
        assert data["error"] == "Invalid or expired token"

    async def test_change_password_token_missing_sub(
        self,
        app_client: QuartTestClient,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test password change with JWT token missing user ID."""
        # Arrange
        mock_token_issuer.verify.return_value = {}  # No 'sub' claim

        # Act
        response = await app_client.post(
            "/v1/auth/change-password",
            json={"current_password": "current", "new_password": "new"},
            headers={"Authorization": "Bearer token.without.sub"},
        )

        # Assert
        assert response.status_code == 401
        data = await response.get_json()
        assert data["error"] == "Invalid token"

    async def test_change_password_missing_fields(
        self,
        app_client: QuartTestClient,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test password change with missing required fields."""
        # Arrange
        mock_token_issuer.verify.return_value = {"sub": "user-123"}

        # Act
        response = await app_client.post(
            "/v1/auth/change-password",
            json={"current_password": "current"},  # Missing new_password
            headers={"Authorization": "Bearer valid.token"},
        )

        # Assert
        assert response.status_code == 400
        data = await response.get_json()
        assert data["error"] == "Current and new passwords are required"

    async def test_change_password_handler_error(
        self,
        app_client: QuartTestClient,
        mock_password_reset_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test password change when handler raises validation error."""
        # Arrange
        from huleedu_service_libs.error_handling.identity_factories import (
            raise_verification_token_invalid_error,
        )

        mock_token_issuer.verify.return_value = {"sub": "user-123"}

        def mock_handler_error(**kwargs: Any) -> NoReturn:
            correlation_id = kwargs.get("correlation_id", uuid4())
            raise_verification_token_invalid_error(
                service="identity_service",
                operation="change_password",
                correlation_id=correlation_id,
            )

        mock_password_reset_handler.change_password.side_effect = mock_handler_error

        # Act
        response = await app_client.post(
            "/v1/auth/change-password",
            json={"current_password": "wrong", "new_password": "new"},
            headers={"Authorization": "Bearer valid.token"},
        )

        # Assert
        assert response.status_code == 400
        data = await response.get_json()
        error_detail = data["error"]
        assert error_detail["error_code"] == "IDENTITY_VERIFICATION_TOKEN_INVALID"
