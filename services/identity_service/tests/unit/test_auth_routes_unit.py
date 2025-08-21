"""
Unit tests for authentication API routes.

Tests the authentication endpoints: POST /v1/auth/login, POST /v1/auth/logout,
and POST /v1/auth/refresh following the established Quart+Dishka testing patterns.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, NoReturn
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from common_core.models.error_models import ErrorDetail
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling import HuleEduError, create_test_error_detail
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.identity_service.api.schemas import (
    RefreshTokenRequest,
    RefreshTokenResponse,
    TokenPair,
)
from services.identity_service.app import app
from services.identity_service.domain_handlers.authentication_handler import (
    AuthenticationHandler,
    LoginResult,
    LogoutResult,
    RefreshResult,
)


class TestAuthRoutes:
    """Test authentication API endpoints using proper Quart+Dishka patterns."""

    @pytest.fixture
    def mock_auth_handler(self) -> AsyncMock:
        """Create mock authentication handler."""
        return AsyncMock(spec=AuthenticationHandler)

    @pytest.fixture
    async def app_client(
        self,
        mock_auth_handler: AsyncMock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        """
        Return a Quart test client configured with mocked dependencies using Dishka.
        This fixture overrides production providers with test providers that supply our mocks.
        """

        # 1. Define a test-specific provider that provides our mocks
        class TestProvider(Provider):
            @provide(scope=Scope.REQUEST)
            def provide_authentication_handler(self) -> AuthenticationHandler:
                return mock_auth_handler

        # 2. Create a new container with our test provider
        container = make_async_container(TestProvider())

        # 3. Apply the container to the app instance for the test
        app.config.update({"TESTING": True})
        QuartDishka(app=app, container=container)

        async with app.test_client() as client:
            yield client

        # 4. Clean up the container after the test
        await container.close()

    async def test_login_success(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test successful user login."""
        # Arrange
        token_pair = TokenPair(
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            expires_in=3600,
        )
        login_result = LoginResult(token_pair)
        mock_auth_handler.login.return_value = login_result

        request_data = {
            "email": "test@example.com",
            "password": "secure-password-123",
        }

        # Act
        response = await app_client.post(
            "/v1/auth/login",
            json=request_data,
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["access_token"] == "test-access-token"
        assert data["refresh_token"] == "test-refresh-token"
        assert data["token_type"] == "Bearer"
        assert data["expires_in"] == 3600

        # Verify handler was called with correct parameters
        mock_auth_handler.login.assert_called_once()
        call_args = mock_auth_handler.login.call_args
        login_request = call_args.kwargs["login_request"]
        assert login_request.email == "test@example.com"
        assert login_request.password == "secure-password-123"
        assert "correlation_id" in call_args.kwargs
        assert "ip_address" in call_args.kwargs

    async def test_login_swedish_email(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test login with Swedish characters in email address."""
        # Arrange
        token_pair = TokenPair(
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            expires_in=3600,
        )
        login_result = LoginResult(token_pair)
        mock_auth_handler.login.return_value = login_result

        request_data = {
            "email": "åsa.öberg@skolan.se",
            "password": "säker-lösenord-123",
        }

        # Act
        response = await app_client.post(
            "/v1/auth/login",
            json=request_data,
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["access_token"] == "test-access-token"

        # Verify handler was called with Swedish email
        mock_auth_handler.login.assert_called_once()
        call_args = mock_auth_handler.login.call_args
        login_request = call_args.kwargs["login_request"]
        assert login_request.email == "åsa.öberg@skolan.se"

    async def test_login_invalid_credentials_error(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test login with invalid credentials returning HuleEduError."""
        # Arrange
        correlation_id = str(uuid4())
        error_detail = create_test_error_detail(
            message="Invalid email or password",
            correlation_id=correlation_id,
            operation="login",
            service="identity_service",
            details={"email": "test@example.com"},
            status_code=401,
        )
        huleedu_error = HuleEduError(error_detail)
        mock_auth_handler.login.side_effect = huleedu_error

        request_data = {
            "email": "test@example.com",
            "password": "wrong-password",
        }

        # Act
        response = await app_client.post(
            "/v1/auth/login",
            json=request_data,
        )

        # Assert
        assert response.status_code == 401
        data = await response.get_json()
        error_response = data["error"]
        assert error_response["error_code"] == "INVALID_CREDENTIALS"
        assert "Invalid email or password" in error_response["message"]
        assert error_response["details"]["email"] == "test@example.com"

    async def test_login_rate_limit_error(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test login rate limiting."""
        # Arrange
        correlation_id = str(uuid4())
        error_detail = ErrorDetail(
            error_code="RATE_LIMIT_EXCEEDED",
            message="Too many login attempts",
            correlation_id=correlation_id,
            operation="login",
            service="identity_service",
            details={"limit": 5, "window_seconds": 60},
            status_code=429,
        )
        huleedu_error = HuleEduError(error_detail)
        mock_auth_handler.login.side_effect = huleedu_error

        request_data = {
            "email": "test@example.com",
            "password": "password123",
        }

        # Act
        response = await app_client.post(
            "/v1/auth/login",
            json=request_data,
        )

        # Assert
        assert response.status_code == 429
        data = await response.get_json()
        error_response = data["error"]
        assert error_response["error_code"] == "RATE_LIMIT_EXCEEDED"
        assert "Too many login attempts" in error_response["message"]

    async def test_login_invalid_json(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test login with invalid JSON payload."""
        # Act
        response = await app_client.post(
            "/v1/auth/login",
            data="invalid-json",
            headers={"Content-Type": "application/json"},
        )

        # Assert
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Internal server error"

    async def test_login_unexpected_error(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test login with unexpected handler error."""
        # Arrange
        mock_auth_handler.login.side_effect = Exception("Database connection failed")

        request_data = {
            "email": "test@example.com",
            "password": "password123",
        }

        # Act
        response = await app_client.post(
            "/v1/auth/login",
            json=request_data,
        )

        # Assert
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Internal server error"

    async def test_logout_success_with_header_token(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test successful logout with token in Authorization header."""
        # Arrange
        logout_result = LogoutResult("Logout successful")
        mock_auth_handler.logout.return_value = logout_result

        # Act
        response = await app_client.post(
            "/v1/auth/logout",
            headers={"Authorization": "Bearer test-refresh-token"},
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["message"] == "Logout successful"

        # Verify handler was called with token
        mock_auth_handler.logout.assert_called_once()
        call_args = mock_auth_handler.logout.call_args
        assert call_args.kwargs["token"] == "test-refresh-token"
        assert "correlation_id" in call_args.kwargs

    async def test_logout_success_with_body_token(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test successful logout with token in request body."""
        # Arrange
        logout_result = LogoutResult("Logout successful")
        mock_auth_handler.logout.return_value = logout_result

        request_data = {"refresh_token": "test-refresh-token"}

        # Act
        response = await app_client.post(
            "/v1/auth/logout",
            json=request_data,
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["message"] == "Logout successful"

        # Verify handler was called with token from body
        mock_auth_handler.logout.assert_called_once()
        call_args = mock_auth_handler.logout.call_args
        assert call_args.kwargs["token"] == "test-refresh-token"

    async def test_logout_no_token(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test logout with no token provided."""
        # Arrange
        correlation_id = str(uuid4())
        error_detail = ErrorDetail(
            error_code="MISSING_TOKEN",
            message="No token provided for logout",
            correlation_id=correlation_id,
            operation="logout",
            service="identity_service",
            status_code=400,
        )
        huleedu_error = HuleEduError(error_detail)
        mock_auth_handler.logout.side_effect = huleedu_error

        # Act
        response = await app_client.post("/v1/auth/logout")

        # Assert
        assert response.status_code == 400
        data = await response.get_json()
        error_response = data["error"]
        assert error_response["error_code"] == "MISSING_TOKEN"

        # Verify handler was called with empty token
        mock_auth_handler.logout.assert_called_once()
        call_args = mock_auth_handler.logout.call_args
        assert call_args.kwargs["token"] == ""

    async def test_logout_unexpected_error(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test logout with unexpected error."""
        # Arrange
        mock_auth_handler.logout.side_effect = Exception("Redis connection failed")

        # Act
        response = await app_client.post(
            "/v1/auth/logout",
            headers={"Authorization": "Bearer test-token"},
        )

        # Assert
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Internal server error"

    async def test_refresh_token_success(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test successful token refresh."""
        # Arrange
        refresh_response = RefreshTokenResponse(
            access_token="new-access-token",
            expires_in=3600,
        )
        refresh_result = RefreshResult(refresh_response)
        mock_auth_handler.refresh_token.return_value = refresh_result

        request_data = {"refresh_token": "valid-refresh-token"}

        # Act
        response = await app_client.post(
            "/v1/auth/refresh",
            json=request_data,
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["access_token"] == "new-access-token"
        assert data["token_type"] == "Bearer"
        assert data["expires_in"] == 3600

        # Verify handler was called with correct request
        mock_auth_handler.refresh_token.assert_called_once()
        call_args = mock_auth_handler.refresh_token.call_args
        refresh_request = call_args.kwargs["refresh_request"]
        assert refresh_request.refresh_token == "valid-refresh-token"
        assert "correlation_id" in call_args.kwargs

    async def test_refresh_token_invalid_token(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test refresh with invalid token."""
        # Arrange
        correlation_id = str(uuid4())
        error_detail = ErrorDetail(
            error_code="INVALID_TOKEN",
            message="Invalid or expired refresh token",
            correlation_id=correlation_id,
            operation="refresh_token",
            service="identity_service",
            status_code=401,
        )
        huleedu_error = HuleEduError(error_detail)
        mock_auth_handler.refresh_token.side_effect = huleedu_error

        request_data = {"refresh_token": "invalid-token"}

        # Act
        response = await app_client.post(
            "/v1/auth/refresh",
            json=request_data,
        )

        # Assert
        assert response.status_code == 401
        data = await response.get_json()
        error_response = data["error"]
        assert error_response["error_code"] == "INVALID_TOKEN"
        assert "Invalid or expired refresh token" in error_response["message"]

    async def test_refresh_token_unexpected_error(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test refresh with unexpected error."""
        # Arrange
        mock_auth_handler.refresh_token.side_effect = Exception("Token store unavailable")

        request_data = {"refresh_token": "valid-token"}

        # Act
        response = await app_client.post(
            "/v1/auth/refresh",
            json=request_data,
        )

        # Assert
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Internal server error"

    @patch("services.identity_service.api.auth_routes.extract_correlation_id")
    async def test_correlation_id_handling(
        self,
        mock_extract_correlation_id: AsyncMock,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test proper correlation ID extraction and usage."""
        # Arrange
        test_correlation_id = uuid4()
        mock_extract_correlation_id.return_value = test_correlation_id

        token_pair = TokenPair(
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            expires_in=3600,
        )
        login_result = LoginResult(token_pair)
        mock_auth_handler.login.return_value = login_result

        request_data = {
            "email": "test@example.com",
            "password": "password123",
        }

        # Act
        response = await app_client.post(
            "/v1/auth/login",
            json=request_data,
        )

        # Assert
        assert response.status_code == 200

        # Verify correlation ID was extracted and passed to handler
        mock_extract_correlation_id.assert_called_once()
        call_args = mock_auth_handler.login.call_args
        assert call_args.kwargs["correlation_id"] == test_correlation_id

    @patch("services.identity_service.api.auth_routes.extract_client_info")
    @patch("services.identity_service.api.auth_routes.parse_device_info")
    async def test_client_info_extraction(
        self,
        mock_parse_device_info: AsyncMock,
        mock_extract_client_info: AsyncMock,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test client information extraction for login."""
        # Arrange
        mock_extract_client_info.return_value = ("192.168.1.100", "Chrome/90.0 User Agent")
        mock_parse_device_info.return_value = ("Chrome", "desktop")

        token_pair = TokenPair(
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            expires_in=3600,
        )
        login_result = LoginResult(token_pair)
        mock_auth_handler.login.return_value = login_result

        request_data = {
            "email": "test@example.com",
            "password": "password123",
        }

        # Act
        response = await app_client.post(
            "/v1/auth/login",
            json=request_data,
        )

        # Assert
        assert response.status_code == 200

        # Verify client info extraction
        mock_extract_client_info.assert_called_once()
        mock_parse_device_info.assert_called_once_with("Chrome/90.0 User Agent")

        # Verify handler received client info
        call_args = mock_auth_handler.login.call_args
        assert call_args.kwargs["ip_address"] == "192.168.1.100"
        assert call_args.kwargs["user_agent"] == "Chrome/90.0 User Agent"
        assert call_args.kwargs["device_name"] == "Chrome"
        assert call_args.kwargs["device_type"] == "desktop"