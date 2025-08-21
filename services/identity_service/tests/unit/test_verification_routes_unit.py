"""
Unit tests for email verification API routes.

Tests the verification endpoints: POST /v1/auth/request-email-verification
and POST /v1/auth/verify-email following the established Quart+Dishka testing patterns.
Focuses on HTTP request/response behavior and DI integration.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling.identity_factories import (
    raise_email_already_verified_error,
    raise_verification_token_expired_error,
    raise_verification_token_invalid_error,
)
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.identity_service.api.schemas import (
    RequestEmailVerificationResponse,
    VerifyEmailResponse,
)
from services.identity_service.app import app
from services.identity_service.domain_handlers.verification_handler import (
    RequestVerificationResult,
    VerificationHandler,
    VerifyEmailResult,
)
from services.identity_service.protocols import TokenIssuer


class TestVerificationRoutes:
    """Test verification API endpoints using proper Quart+Dishka patterns."""

    @pytest.fixture
    def mock_verification_handler(self) -> AsyncMock:
        """Create mock verification handler."""
        from services.identity_service.domain_handlers.verification_handler import (
            VerificationHandler,
        )

        return AsyncMock(spec=VerificationHandler)

    @pytest.fixture
    def mock_token_issuer(self) -> AsyncMock:
        """Create mock token issuer."""
        return AsyncMock(spec=TokenIssuer)

    @pytest.fixture
    async def app_client(
        self,
        mock_verification_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        """
        Return a Quart test client configured with mocked dependencies using Dishka.
        This fixture overrides production providers with test providers that supply our mocks.
        """

        # 1. Define a test-specific provider that provides our mocks
        class TestProvider(Provider):
            @provide(scope=Scope.REQUEST)
            def provide_verification_handler(self) -> VerificationHandler:
                return mock_verification_handler

            @provide(scope=Scope.APP)
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

    async def test_request_email_verification_success(
        self,
        app_client: QuartTestClient,
        mock_verification_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test successful email verification request with valid JWT."""
        # Arrange
        user_id = "user-123"
        correlation_id = "12345678-1234-5678-9abc-123456789abc"
        jwt_token = "valid.jwt.token"

        # Mock JWT verification
        mock_token_issuer.verify.return_value = {"sub": user_id}

        # Mock verification handler result
        response_data = RequestEmailVerificationResponse(
            message="Email verification token generated successfully",
            correlation_id=correlation_id,
        )
        result = RequestVerificationResult(response_data)
        mock_verification_handler.request_email_verification.return_value = result

        # Act
        response = await app_client.post(
            "/v1/auth/request-email-verification",
            json={},
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "X-Correlation-ID": correlation_id,
            },
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["message"] == "Email verification token generated successfully"
        assert data["correlation_id"] == correlation_id

        # Verify JWT token was verified
        mock_token_issuer.verify.assert_called_once_with(jwt_token)

        # Verify verification handler was called
        mock_verification_handler.request_email_verification.assert_called_once()
        call_args = mock_verification_handler.request_email_verification.call_args
        assert call_args.kwargs["user_id"] == user_id

    async def test_request_email_verification_no_auth_header(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test email verification request without Authorization header."""
        # Act
        response = await app_client.post(
            "/v1/auth/request-email-verification",
            json={},
        )

        # Assert
        assert response.status_code == 401
        data = await response.get_json()
        assert data["error"] == "Authorization token required"

    async def test_request_email_verification_invalid_jwt(
        self,
        app_client: QuartTestClient,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test email verification request with invalid JWT token."""
        # Arrange
        jwt_token = "invalid.jwt.token"
        mock_token_issuer.verify.side_effect = Exception("Invalid token")

        # Act
        response = await app_client.post(
            "/v1/auth/request-email-verification",
            json={},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )

        # Assert
        assert response.status_code == 401
        data = await response.get_json()
        assert data["error"] == "Invalid or expired token"

    async def test_request_email_verification_jwt_no_sub(
        self,
        app_client: QuartTestClient,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test email verification request with JWT missing sub claim."""
        # Arrange
        jwt_token = "valid.jwt.token"
        mock_token_issuer.verify.return_value = {}  # No 'sub' claim

        # Act
        response = await app_client.post(
            "/v1/auth/request-email-verification",
            json={},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )

        # Assert
        assert response.status_code == 401
        data = await response.get_json()
        assert data["error"] == "Invalid token"

    async def test_request_email_verification_handler_error(
        self,
        app_client: QuartTestClient,
        mock_verification_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test email verification request when handler raises HuleEduError."""
        # Arrange
        user_id = "user-123"
        correlation_id = "12345678-1234-5678-9abc-123456789abc"
        jwt_token = "valid.jwt.token"

        # Mock JWT verification
        mock_token_issuer.verify.return_value = {"sub": user_id}

        # Mock handler raising HuleEduError
        def mock_error(*_: Any, **__: Any) -> None:
            raise_email_already_verified_error(
                service="identity_service",
                operation="request_email_verification",
                email="test@example.com",
                correlation_id=UUID(correlation_id),
            )

        mock_verification_handler.request_email_verification.side_effect = mock_error

        # Act
        response = await app_client.post(
            "/v1/auth/request-email-verification",
            json={},
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "X-Correlation-ID": correlation_id,
            },
        )

        # Assert
        assert response.status_code == 400
        data = await response.get_json()
        error_detail = data["error"]
        assert "Email is already verified" in error_detail["message"]
        assert error_detail["error_code"] == "IDENTITY_EMAIL_ALREADY_VERIFIED"

    async def test_request_email_verification_swedish_user(
        self,
        app_client: QuartTestClient,
        mock_verification_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test email verification request for Swedish user with special characters."""
        # Arrange
        user_id = "åsa-öberg-123"
        correlation_id = "12345678-1234-5678-9abc-123456789abc"
        jwt_token = "valid.jwt.token"

        # Mock JWT verification
        mock_token_issuer.verify.return_value = {"sub": user_id}

        # Mock verification handler result
        response_data = RequestEmailVerificationResponse(
            message="Email verification token generated successfully",
            correlation_id=correlation_id,
        )
        result = RequestVerificationResult(response_data)
        mock_verification_handler.request_email_verification.return_value = result

        # Act
        response = await app_client.post(
            "/v1/auth/request-email-verification",
            json={},
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "X-Correlation-ID": correlation_id,
            },
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["message"] == "Email verification token generated successfully"

        # Verify handler called with Swedish user ID
        call_args = mock_verification_handler.request_email_verification.call_args
        assert call_args.kwargs["user_id"] == user_id

    async def test_verify_email_success(
        self,
        app_client: QuartTestClient,
        mock_verification_handler: AsyncMock,
    ) -> None:
        """Test successful email verification with valid token."""
        # Arrange
        verification_token = "valid-verification-token"
        correlation_id = "12345678-1234-5678-9abc-123456789abc"

        # Mock verification handler result
        response_data = VerifyEmailResponse(message="Email verified successfully")
        result = VerifyEmailResult(response_data)
        mock_verification_handler.verify_email.return_value = result

        # Act
        response = await app_client.post(
            "/v1/auth/verify-email",
            json={"token": verification_token},
            headers={"X-Correlation-ID": correlation_id},
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["message"] == "Email verified successfully"

        # Verify handler called with correct token
        mock_verification_handler.verify_email.assert_called_once()
        call_args = mock_verification_handler.verify_email.call_args
        assert call_args.kwargs["verify_request"].token == verification_token

    async def test_verify_email_invalid_token(
        self,
        app_client: QuartTestClient,
        mock_verification_handler: AsyncMock,
    ) -> None:
        """Test email verification with invalid token."""
        # Arrange
        verification_token = "invalid-token"
        correlation_id = "12345678-1234-5678-9abc-123456789abc"

        # Mock handler raising HuleEduError for invalid token
        def mock_error(*_: Any, **__: Any) -> None:
            raise_verification_token_invalid_error(
                service="identity_service",
                operation="verify_email",
                correlation_id=UUID(correlation_id),
            )

        mock_verification_handler.verify_email.side_effect = mock_error

        # Act
        response = await app_client.post(
            "/v1/auth/verify-email",
            json={"token": verification_token},
            headers={"X-Correlation-ID": correlation_id},
        )

        # Assert
        assert response.status_code == 400
        data = await response.get_json()
        error_detail = data["error"]
        assert "Email verification token is invalid" in error_detail["message"]
        assert error_detail["error_code"] == "IDENTITY_VERIFICATION_TOKEN_INVALID"

    async def test_verify_email_expired_token(
        self,
        app_client: QuartTestClient,
        mock_verification_handler: AsyncMock,
    ) -> None:
        """Test email verification with expired token."""
        # Arrange
        verification_token = "expired-token"
        correlation_id = "12345678-1234-5678-9abc-123456789abc"

        # Mock handler raising HuleEduError for expired token
        def mock_error(*_: Any, **__: Any) -> None:
            raise_verification_token_expired_error(
                service="identity_service",
                operation="verify_email",
                correlation_id=UUID(correlation_id),
            )

        mock_verification_handler.verify_email.side_effect = mock_error

        # Act
        response = await app_client.post(
            "/v1/auth/verify-email",
            json={"token": verification_token},
            headers={"X-Correlation-ID": correlation_id},
        )

        # Assert
        assert response.status_code == 400
        data = await response.get_json()
        error_detail = data["error"]
        assert "Email verification token has expired" in error_detail["message"]
        assert error_detail["error_code"] == "IDENTITY_VERIFICATION_TOKEN_EXPIRED"

    async def test_verify_email_missing_token(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test email verification with missing token in request body."""
        # Act
        response = await app_client.post(
            "/v1/auth/verify-email",
            json={},
        )

        # Assert - Pydantic validation should catch missing required field
        assert response.status_code == 500  # Quart returns 500 for validation errors

    async def test_verify_email_malformed_json(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test email verification with malformed JSON request."""
        # Act
        response = await app_client.post(
            "/v1/auth/verify-email",
            data="invalid json",
            headers={"Content-Type": "application/json"},
        )

        # Assert
        assert response.status_code == 500  # Quart returns 500 for JSON parsing errors

    async def test_verify_email_swedish_context(
        self,
        app_client: QuartTestClient,
        mock_verification_handler: AsyncMock,
    ) -> None:
        """Test email verification in Swedish context with UTF-8 characters."""
        # Arrange
        verification_token = "åäö-verification-token-ÅÄÖ"
        correlation_id = "12345678-1234-5678-9abc-123456789abc"

        # Mock verification handler result
        response_data = VerifyEmailResponse(message="E-post verifierad framgångsrikt")
        result = VerifyEmailResult(response_data)
        mock_verification_handler.verify_email.return_value = result

        # Act
        response = await app_client.post(
            "/v1/auth/verify-email",
            json={"token": verification_token},
            headers={"X-Correlation-ID": correlation_id},
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["message"] == "E-post verifierad framgångsrikt"

        # Verify handler called with Swedish token
        call_args = mock_verification_handler.verify_email.call_args
        assert call_args.kwargs["verify_request"].token == verification_token

    async def test_correlation_id_handling(
        self,
        app_client: QuartTestClient,
        mock_verification_handler: AsyncMock,
    ) -> None:
        """Test proper correlation ID handling across verification endpoints."""
        # Arrange
        verification_token = "test-token"
        correlation_id = "12345678-1234-5678-9abc-123456789abc"

        # Mock verification handler result
        response_data = VerifyEmailResponse(message="Email verified successfully")
        result = VerifyEmailResult(response_data)
        mock_verification_handler.verify_email.return_value = result

        # Act
        response = await app_client.post(
            "/v1/auth/verify-email",
            json={"token": verification_token},
            headers={"X-Correlation-ID": correlation_id},
        )

        # Assert
        assert response.status_code == 200

        # Verify correlation ID passed to handler
        call_args = mock_verification_handler.verify_email.call_args
        assert str(call_args.kwargs["correlation_id"]) == correlation_id

    async def test_unexpected_server_error(
        self,
        app_client: QuartTestClient,
        mock_verification_handler: AsyncMock,
    ) -> None:
        """Test handling of unexpected server errors."""
        # Arrange
        verification_token = "test-token"
        mock_verification_handler.verify_email.side_effect = Exception("Database connection failed")

        # Act
        response = await app_client.post(
            "/v1/auth/verify-email",
            json={"token": verification_token},
        )

        # Assert
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Internal server error"
