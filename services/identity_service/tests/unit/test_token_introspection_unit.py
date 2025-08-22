"""
Unit tests for token introspection functionality.

Tests the token introspection endpoint: POST /v1/auth/introspect,
and related schema validation following the established Quart+Dishka testing patterns.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling import HuleEduError, create_test_error_detail
from pydantic import ValidationError
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.identity_service.api.schemas import (
    IntrospectRequest,
    IntrospectResponse,
)
from services.identity_service.app import app
from services.identity_service.domain_handlers.authentication_handler import (
    AuthenticationHandler,
    IntrospectResult,
)


class TestTokenIntrospectionRoute:
    """Test token introspection API endpoint using proper Quart+Dishka patterns."""

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

    async def test_introspect_active_access_token(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test introspection of active access token."""
        # Arrange
        introspect_response = IntrospectResponse(
            active=True,
            sub="user-123",
            exp=1234567890,
            iat=1234564290,
            jti=None,
            org_id="org-456",
            roles=["teacher", "admin"],
            token_type="access_token",
        )
        introspect_result = IntrospectResult(introspect_response)
        mock_auth_handler.introspect_token.return_value = introspect_result

        request_data = {"token": "valid-access-token"}

        # Act
        response = await app_client.post(
            "/v1/auth/introspect",
            json=request_data,
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["active"] is True
        assert data["sub"] == "user-123"
        assert data["exp"] == 1234567890
        assert data["iat"] == 1234564290
        assert data["jti"] is None
        assert data["org_id"] == "org-456"
        assert data["roles"] == ["teacher", "admin"]
        assert data["token_type"] == "access_token"

        # Verify handler was called with correct parameters
        mock_auth_handler.introspect_token.assert_called_once()
        call_args = mock_auth_handler.introspect_token.call_args
        assert call_args.kwargs["token"] == "valid-access-token"
        assert "correlation_id" in call_args.kwargs

    async def test_introspect_active_refresh_token(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test introspection of active refresh token."""
        # Arrange
        introspect_response = IntrospectResponse(
            active=True,
            sub="user-789",
            exp=1234567890,
            iat=1234564290,
            jti="refresh-jti-123",
            org_id="org-456",
            roles=["student"],
            token_type="refresh_token",
        )
        introspect_result = IntrospectResult(introspect_response)
        mock_auth_handler.introspect_token.return_value = introspect_result

        request_data = {"token": "valid-refresh-token"}

        # Act
        response = await app_client.post(
            "/v1/auth/introspect",
            json=request_data,
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["active"] is True
        assert data["sub"] == "user-789"
        assert data["jti"] == "refresh-jti-123"
        assert data["roles"] == ["student"]
        assert data["token_type"] == "refresh_token"

        # Verify handler was called with correct parameters
        mock_auth_handler.introspect_token.assert_called_once()
        call_args = mock_auth_handler.introspect_token.call_args
        assert call_args.kwargs["token"] == "valid-refresh-token"

    async def test_introspect_inactive_token(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test introspection of inactive/invalid token."""
        # Arrange
        introspect_response = IntrospectResponse(active=False)
        introspect_result = IntrospectResult(introspect_response)
        mock_auth_handler.introspect_token.return_value = introspect_result

        request_data = {"token": "invalid-token"}

        # Act
        response = await app_client.post(
            "/v1/auth/introspect",
            json=request_data,
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["active"] is False
        assert data["sub"] is None
        assert data["exp"] is None
        assert data["iat"] is None
        assert data["jti"] is None
        assert data["org_id"] is None
        assert data["roles"] == []
        assert data["token_type"] == "access_token"  # Default value

        # Verify handler was called
        mock_auth_handler.introspect_token.assert_called_once()

    async def test_introspect_swedish_user_context(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test introspection with Swedish context (roles, org names)."""
        # Arrange
        introspect_response = IntrospectResponse(
            active=True,
            sub="åsa-öberg-123",
            exp=1234567890,
            iat=1234564290,
            org_id="skolan-västerås-456",
            roles=["lärare", "rektor"],
            token_type="access_token",
        )
        introspect_result = IntrospectResult(introspect_response)
        mock_auth_handler.introspect_token.return_value = introspect_result

        request_data = {"token": "swedish-context-token"}

        # Act
        response = await app_client.post(
            "/v1/auth/introspect",
            json=request_data,
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["active"] is True
        assert data["sub"] == "åsa-öberg-123"
        assert data["org_id"] == "skolan-västerås-456"
        assert data["roles"] == ["lärare", "rektor"]

    @pytest.mark.parametrize(
        "error_message, expected_status",
        [
            ("Token validation failed", 400),
            ("Invalid token format", 400),
            ("Token has been revoked", 400),
        ],
    )
    async def test_introspect_handler_errors(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
        error_message: str,
        expected_status: int,
    ) -> None:
        """Test introspection with various handler errors."""
        # Arrange
        correlation_id = str(uuid4())
        error_detail = create_test_error_detail(
            message=error_message,
            correlation_id=correlation_id,
            operation="introspect_token",
            service="identity_service",
            details={"token": "problematic-token"},
        )
        huleedu_error = HuleEduError(error_detail)
        mock_auth_handler.introspect_token.side_effect = huleedu_error

        request_data = {"token": "problematic-token"}

        # Act
        response = await app_client.post(
            "/v1/auth/introspect",
            json=request_data,
        )

        # Assert
        assert response.status_code == expected_status
        data = await response.get_json()
        error_response = data["error"]
        assert error_message in error_response["message"]
        assert error_response["details"]["token"] == "problematic-token"

    async def test_introspect_unexpected_error(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test introspection with unexpected handler error."""
        # Arrange
        mock_auth_handler.introspect_token.side_effect = Exception("Token store unavailable")

        request_data = {"token": "valid-token"}

        # Act
        response = await app_client.post(
            "/v1/auth/introspect",
            json=request_data,
        )

        # Assert
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Internal server error"

    async def test_introspect_invalid_json(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test introspection with invalid JSON payload."""
        # Act
        response = await app_client.post(
            "/v1/auth/introspect",
            data="invalid-json",
            headers={"Content-Type": "application/json"},
        )

        # Assert
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Internal server error"


class TestIntrospectResult:
    """Test IntrospectResult class functionality."""

    def test_introspect_result_to_dict_active_token(self) -> None:
        """Test IntrospectResult.to_dict() with active token response."""
        # Arrange
        response = IntrospectResponse(
            active=True,
            sub="user-123",
            exp=1234567890,
            iat=1234564290,
            jti="jti-456",
            org_id="org-789",
            roles=["teacher", "admin"],
            token_type="refresh_token",
        )
        result = IntrospectResult(response)

        # Act
        dict_result = result.to_dict()

        # Assert
        assert dict_result["active"] is True
        assert dict_result["sub"] == "user-123"
        assert dict_result["exp"] == 1234567890
        assert dict_result["iat"] == 1234564290
        assert dict_result["jti"] == "jti-456"
        assert dict_result["org_id"] == "org-789"
        assert dict_result["roles"] == ["teacher", "admin"]
        assert dict_result["token_type"] == "refresh_token"

    def test_introspect_result_to_dict_inactive_token(self) -> None:
        """Test IntrospectResult.to_dict() with inactive token response."""
        # Arrange
        response = IntrospectResponse(active=False)
        result = IntrospectResult(response)

        # Act
        dict_result = result.to_dict()

        # Assert
        assert dict_result["active"] is False
        assert dict_result["sub"] is None
        assert dict_result["exp"] is None
        assert dict_result["iat"] is None
        assert dict_result["jti"] is None
        assert dict_result["org_id"] is None
        assert dict_result["roles"] == []
        assert dict_result["token_type"] == "access_token"


class TestIntrospectSchemas:
    """Test IntrospectRequest and IntrospectResponse schema validation."""

    def test_introspect_request_valid_data(self) -> None:
        """Test IntrospectRequest with valid data."""
        # Act
        request = IntrospectRequest(token="valid-token-string")

        # Assert
        assert request.token == "valid-token-string"

    @pytest.mark.parametrize(
        "token_value",
        [
            "",  # Empty string - valid but not useful
            "   ",  # Whitespace only - valid but not useful  
            "very-long-jwt-token-that-could-be-real",  # Long token
        ],
    )
    def test_introspect_request_edge_case_tokens(self, token_value: str) -> None:
        """Test IntrospectRequest with edge case but valid token values."""
        # Act
        request = IntrospectRequest(token=token_value)

        # Assert - Pydantic allows these values as they are valid strings
        assert request.token == token_value

    def test_introspect_request_invalid_none_token(self) -> None:
        """Test IntrospectRequest validation with None token (should fail)."""
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            IntrospectRequest(token=None)  # type: ignore
        
        # Verify the validation error
        error = exc_info.value
        assert "string_type" in str(error)

    def test_introspect_response_defaults(self) -> None:
        """Test IntrospectResponse default values."""
        # Act
        response = IntrospectResponse(active=False)

        # Assert
        assert response.active is False
        assert response.sub is None
        assert response.exp is None
        assert response.iat is None
        assert response.jti is None
        assert response.org_id is None
        assert response.roles == []
        assert response.token_type == "access_token"

    def test_introspect_response_full_data(self) -> None:
        """Test IntrospectResponse with full data."""
        # Act
        response = IntrospectResponse(
            active=True,
            sub="user-456",
            exp=1234567890,
            iat=1234564290,
            jti="jti-789",
            org_id="org-123",
            roles=["teacher", "admin", "moderator"],
            token_type="refresh_token",
        )

        # Assert
        assert response.active is True
        assert response.sub == "user-456"
        assert response.exp == 1234567890
        assert response.iat == 1234564290
        assert response.jti == "jti-789"
        assert response.org_id == "org-123"
        assert response.roles == ["teacher", "admin", "moderator"]
        assert response.token_type == "refresh_token"

    def test_introspect_response_model_dump(self) -> None:
        """Test IntrospectResponse serialization via model_dump."""
        # Arrange
        response = IntrospectResponse(
            active=True,
            sub="user-serialization",
            roles=["student"],
        )

        # Act
        dumped = response.model_dump(mode="json")

        # Assert
        assert isinstance(dumped, dict)
        assert dumped["active"] is True
        assert dumped["sub"] == "user-serialization"
        assert dumped["roles"] == ["student"]
        assert "token_type" in dumped

    def test_introspect_response_swedish_characters(self) -> None:
        """Test IntrospectResponse handles Swedish characters properly."""
        # Arrange
        response = IntrospectResponse(
            active=True,
            sub="åsa-öberg-user",
            org_id="västerås-skolan",
            roles=["lärare", "språklärare"],
        )

        # Act
        dumped = response.model_dump(mode="json")

        # Assert
        assert dumped["sub"] == "åsa-öberg-user"
        assert dumped["org_id"] == "västerås-skolan"
        assert dumped["roles"] == ["lärare", "språklärare"]