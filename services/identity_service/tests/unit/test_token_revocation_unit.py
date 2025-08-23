"""
Unit tests for token revocation functionality.

Tests the token revocation endpoint POST /v1/auth/revoke,
AuthenticationHandler.revoke_token() method, RevokeResult class, and schema validation
following the established Quart+Dishka testing patterns.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling import HuleEduError, create_test_error_detail
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.identity_service.api.schemas import (
    RevokeTokenRequest,
    RevokeTokenResponse,
)
from services.identity_service.app import app
from services.identity_service.domain_handlers.authentication_handler import (
    AuthenticationHandler,
    RevokeResult,
)
from services.identity_service.protocols import (
    IdentityEventPublisherProtocol,
    SessionRepo,
    TokenIssuer,
)


class TestTokenRevocationRoutes:
    """Test token revocation API endpoints using proper Quart+Dishka patterns."""

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

    async def test_revoke_token_success_refresh_token(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test successful refresh token revocation."""
        # Arrange
        revoke_response = RevokeTokenResponse(revoked=True)
        revoke_result = RevokeResult(revoke_response)
        mock_auth_handler.revoke_token.return_value = revoke_result

        request_data = {
            "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.test",
            "token_type_hint": "refresh_token",
        }

        # Act
        response = await app_client.post(
            "/v1/auth/revoke",
            json=request_data,
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["revoked"] is True

        # Verify handler was called with correct parameters
        mock_auth_handler.revoke_token.assert_called_once()
        call_args = mock_auth_handler.revoke_token.call_args
        assert call_args.kwargs["token"] == "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.test"
        assert call_args.kwargs["token_type_hint"] == "refresh_token"
        assert "correlation_id" in call_args.kwargs
        assert isinstance(call_args.kwargs["correlation_id"], UUID)

    async def test_revoke_token_success_access_token(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test successful access token revocation."""
        # Arrange
        revoke_response = RevokeTokenResponse(revoked=True)
        revoke_result = RevokeResult(revoke_response)
        mock_auth_handler.revoke_token.return_value = revoke_result

        request_data = {
            "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.access",
            "token_type_hint": "access_token",
        }

        # Act
        response = await app_client.post(
            "/v1/auth/revoke",
            json=request_data,
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["revoked"] is True

        # Verify handler was called with access token hint
        mock_auth_handler.revoke_token.assert_called_once()
        call_args = mock_auth_handler.revoke_token.call_args
        assert call_args.kwargs["token_type_hint"] == "access_token"

    async def test_revoke_token_default_hint(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test token revocation with default token_type_hint."""
        # Arrange
        revoke_response = RevokeTokenResponse(revoked=True)
        revoke_result = RevokeResult(revoke_response)
        mock_auth_handler.revoke_token.return_value = revoke_result

        request_data = {
            "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.test",
        }

        # Act
        response = await app_client.post(
            "/v1/auth/revoke",
            json=request_data,
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["revoked"] is True

        # Verify handler was called with default hint
        mock_auth_handler.revoke_token.assert_called_once()
        call_args = mock_auth_handler.revoke_token.call_args
        assert call_args.kwargs["token_type_hint"] == "refresh_token"

    async def test_revoke_token_invalid_json(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test token revocation with invalid JSON payload."""
        # Act
        response = await app_client.post(
            "/v1/auth/revoke",
            data="invalid-json",
            headers={"Content-Type": "application/json"},
        )

        # Assert
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Internal server error"

    async def test_revoke_token_missing_token_field(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test token revocation with missing required token field."""
        # Act
        response = await app_client.post(
            "/v1/auth/revoke",
            json={"token_type_hint": "refresh_token"},
        )

        # Assert
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Internal server error"

    async def test_revoke_token_huleedu_error(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test token revocation with HuleEduError from handler."""
        # Arrange
        correlation_id = str(uuid4())
        error_detail = create_test_error_detail(
            message="Token verification failed",
            correlation_id=correlation_id,
            operation="revoke_token",
            service="identity_service",
            details={"token_format": "invalid"},
        )
        huleedu_error = HuleEduError(error_detail)
        mock_auth_handler.revoke_token.side_effect = huleedu_error

        request_data = {
            "token": "invalid-token-format",
            "token_type_hint": "refresh_token",
        }

        # Act
        response = await app_client.post(
            "/v1/auth/revoke",
            json=request_data,
        )

        # Assert
        assert response.status_code == 400
        data = await response.get_json()
        error_response = data["error"]
        assert "Token verification failed" in error_response["message"]
        assert error_response["details"]["token_format"] == "invalid"

    async def test_revoke_token_unexpected_error(
        self,
        app_client: QuartTestClient,
        mock_auth_handler: AsyncMock,
    ) -> None:
        """Test token revocation with unexpected handler error."""
        # Arrange
        mock_auth_handler.revoke_token.side_effect = Exception("Session store unavailable")

        request_data = {
            "token": "valid-token",
            "token_type_hint": "refresh_token",
        }

        # Act
        response = await app_client.post(
            "/v1/auth/revoke",
            json=request_data,
        )

        # Assert
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Internal server error"


class TestAuthenticationHandlerRevokeToken:
    """Test AuthenticationHandler.revoke_token() method behavior."""

    @pytest.fixture
    def mock_token_issuer(self) -> AsyncMock:
        """Create mock token issuer."""
        return AsyncMock(spec=TokenIssuer)

    @pytest.fixture
    def mock_session_repo(self) -> AsyncMock:
        """Create mock session repository."""
        return AsyncMock(spec=SessionRepo)

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher."""
        return AsyncMock(spec=IdentityEventPublisherProtocol)

    @pytest.fixture
    def auth_handler(
        self,
        mock_token_issuer: AsyncMock,
        mock_session_repo: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> AuthenticationHandler:
        """Create AuthenticationHandler with mocked dependencies."""
        # Create with mocked dependencies
        handler = AuthenticationHandler.__new__(AuthenticationHandler)
        handler._token_issuer = mock_token_issuer
        handler._session_repo = mock_session_repo
        handler._event_publisher = mock_event_publisher
        return handler

    @pytest.mark.parametrize(
        "claims, expected_jti, expected_user_id",
        [
            # Refresh token with JTI
            (
                {"jti": "token-123", "sub": "user-456", "token_type": "refresh"},
                "token-123",
                "user-456",
            ),
            # Access token without JTI
            (
                {"sub": "user-789", "token_type": "access"},
                None,
                "user-789",
            ),
        ],
    )
    async def test_revoke_token_success_with_valid_token(
        self,
        auth_handler: AuthenticationHandler,
        mock_token_issuer: AsyncMock,
        mock_session_repo: AsyncMock,
        mock_event_publisher: AsyncMock,
        claims: dict,
        expected_jti: str | None,
        expected_user_id: str,
    ) -> None:
        """Test successful token revocation with valid token claims."""
        # Arrange
        mock_token_issuer.verify.return_value = claims
        correlation_id = uuid4()

        # Act
        result = await auth_handler.revoke_token(
            token="valid-jwt-token",
            token_type_hint="refresh_token",
            correlation_id=correlation_id,
        )

        # Assert
        assert isinstance(result, RevokeResult)
        assert result.response.revoked is True

        # Verify token verification was called
        mock_token_issuer.verify.assert_called_once_with("valid-jwt-token")

        # Verify session revocation only for refresh tokens with JTI
        if expected_jti:
            mock_session_repo.revoke_refresh.assert_called_once_with(expected_jti)
            mock_event_publisher.publish_token_revoked.assert_called_once_with(
                user_id=expected_user_id,
                jti=expected_jti,
                reason="user_request",
                correlation_id=correlation_id,
            )
        else:
            mock_session_repo.revoke_refresh.assert_not_called()
            mock_event_publisher.publish_token_revoked.assert_not_called()

    async def test_revoke_token_invalid_token_returns_success(
        self,
        auth_handler: AuthenticationHandler,
        mock_token_issuer: AsyncMock,
        mock_session_repo: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test token revocation with invalid token returns success per RFC 7009."""
        # Arrange
        mock_token_issuer.verify.return_value = None  # Invalid token
        correlation_id = uuid4()

        # Act
        result = await auth_handler.revoke_token(
            token="invalid-token",
            token_type_hint="refresh_token",
            correlation_id=correlation_id,
        )

        # Assert
        assert isinstance(result, RevokeResult)
        assert result.response.revoked is True

        # Verify no session operations were performed
        mock_session_repo.revoke_refresh.assert_not_called()
        mock_event_publisher.publish_token_revoked.assert_not_called()

    async def test_revoke_token_exception_returns_success(
        self,
        auth_handler: AuthenticationHandler,
        mock_token_issuer: AsyncMock,
        mock_session_repo: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test token revocation with exception returns success per RFC 7009."""
        # Arrange
        mock_token_issuer.verify.side_effect = Exception("Token parsing failed")
        correlation_id = uuid4()

        # Act
        result = await auth_handler.revoke_token(
            token="malformed-token",
            token_type_hint="refresh_token",
            correlation_id=correlation_id,
        )

        # Assert
        assert isinstance(result, RevokeResult)
        assert result.response.revoked is True

        # Verify no session operations were performed
        mock_session_repo.revoke_refresh.assert_not_called()
        mock_event_publisher.publish_token_revoked.assert_not_called()

    async def test_revoke_token_session_repo_exception_returns_success(
        self,
        auth_handler: AuthenticationHandler,
        mock_token_issuer: AsyncMock,
        mock_session_repo: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test token revocation with session repo exception returns success."""
        # Arrange
        claims = {"jti": "token-123", "sub": "user-456"}
        mock_token_issuer.verify.return_value = claims
        mock_session_repo.revoke_refresh.side_effect = Exception("Database error")
        correlation_id = uuid4()

        # Act
        result = await auth_handler.revoke_token(
            token="valid-token",
            token_type_hint="refresh_token",
            correlation_id=correlation_id,
        )

        # Assert
        assert isinstance(result, RevokeResult)
        assert result.response.revoked is True

        # Verify attempt was made to revoke
        mock_session_repo.revoke_refresh.assert_called_once_with("token-123")
        # Event publishing should not be called due to exception
        mock_event_publisher.publish_token_revoked.assert_not_called()


class TestRevokeResult:
    """Test RevokeResult class functionality."""

    def test_revoke_result_initialization(self) -> None:
        """Test RevokeResult can be initialized with RevokeTokenResponse."""
        # Arrange
        response = RevokeTokenResponse(revoked=True)

        # Act
        result = RevokeResult(response)

        # Assert
        assert result.response is response
        assert result.response.revoked is True

    def test_revoke_result_to_dict(self) -> None:
        """Test RevokeResult.to_dict() conversion."""
        # Arrange
        response = RevokeTokenResponse(revoked=True)
        result = RevokeResult(response)

        # Act
        dict_result = result.to_dict()

        # Assert
        assert isinstance(dict_result, dict)
        assert dict_result == {"revoked": True}

    def test_revoke_result_to_dict_false(self) -> None:
        """Test RevokeResult.to_dict() with revoked=False."""
        # Arrange
        response = RevokeTokenResponse(revoked=False)
        result = RevokeResult(response)

        # Act
        dict_result = result.to_dict()

        # Assert
        assert isinstance(dict_result, dict)
        assert dict_result == {"revoked": False}


class TestRevokeTokenSchemas:
    """Test RevokeTokenRequest and RevokeTokenResponse schema validation."""

    @pytest.mark.parametrize(
        "token, token_type_hint, expected_hint",
        [
            # Standard refresh token request
            ("eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.test", "refresh_token", "refresh_token"),
            # Access token request
            ("eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.access", "access_token", "access_token"),
            # Default hint when not provided
            ("eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.default", None, "refresh_token"),
        ],
    )
    def test_revoke_token_request_validation(
        self,
        token: str,
        token_type_hint: str | None,
        expected_hint: str,
    ) -> None:
        """Test RevokeTokenRequest schema validation with various inputs."""
        # Arrange
        data = {"token": token}
        if token_type_hint is not None:
            data["token_type_hint"] = token_type_hint

        # Act
        request = RevokeTokenRequest(**data)

        # Assert
        assert request.token == token
        assert request.token_type_hint == expected_hint

    def test_revoke_token_request_missing_token_raises_error(self) -> None:
        """Test RevokeTokenRequest validation fails without required token."""
        # Act & Assert - empty string is valid, only missing field should raise
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            # Use model_validate with a dict missing the required token field
            RevokeTokenRequest.model_validate({"token_type_hint": "refresh_token"})

    def test_revoke_token_request_empty_token_valid(self) -> None:
        """Test RevokeTokenRequest accepts empty token string."""
        # Act
        request = RevokeTokenRequest(token="", token_type_hint="refresh_token")

        # Assert
        assert request.token == ""
        assert request.token_type_hint == "refresh_token"

    @pytest.mark.parametrize(
        "revoked_status",
        [True, False],
    )
    def test_revoke_token_response_validation(self, revoked_status: bool) -> None:
        """Test RevokeTokenResponse schema validation."""
        # Act
        response = RevokeTokenResponse(revoked=revoked_status)

        # Assert
        assert response.revoked is revoked_status

    def test_revoke_token_response_model_dump(self) -> None:
        """Test RevokeTokenResponse model_dump() for JSON serialization."""
        # Arrange
        response = RevokeTokenResponse(revoked=True)

        # Act
        json_data = response.model_dump(mode="json")

        # Assert
        assert isinstance(json_data, dict)
        assert json_data == {"revoked": True}
