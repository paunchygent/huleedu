"""
Unit tests for session management API routes.

Tests the session management endpoints: GET /v1/auth/sessions,
DELETE /v1/auth/sessions/<session_id>, DELETE /v1/auth/sessions,
and GET /v1/auth/sessions/active following the established Quart+Dishka testing patterns.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling import HuleEduError, create_test_error_detail
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.identity_service.app import app
from services.identity_service.domain_handlers.session_management_handler import (
    ActiveSessionCountResult,
    SessionActionResult,
    SessionInfo,
    SessionListResult,
    SessionManagementHandler,
)
from services.identity_service.protocols import TokenIssuer


class TestSessionRoutes:
    """Test session management API endpoints using proper Quart+Dishka patterns."""

    @pytest.fixture
    def mock_session_handler(self) -> AsyncMock:
        """Create mock session management handler."""
        return AsyncMock(spec=SessionManagementHandler)

    @pytest.fixture
    def mock_token_issuer(self) -> AsyncMock:
        """Create mock token issuer."""
        return AsyncMock(spec=TokenIssuer)

    @pytest.fixture
    async def app_client(
        self,
        mock_session_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        """
        Return a Quart test client configured with mocked dependencies using Dishka.
        This fixture overrides production providers with test providers that supply our mocks.
        """

        # 1. Define a test-specific provider that provides our mocks
        class TestProvider(Provider):
            @provide(scope=Scope.REQUEST)
            def provide_session_handler(self) -> SessionManagementHandler:
                return mock_session_handler

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

    def _create_test_session_info(
        self,
        jti: str = "test-jti-123",
        device_name: str | None = "Chrome",
        device_type: str | None = "desktop",
        ip_address: str | None = "192.168.1.100",
        is_current: bool = False,
    ) -> SessionInfo:
        """Create test session info object."""
        return SessionInfo(
            jti=jti,
            device_name=device_name,
            device_type=device_type,
            ip_address=ip_address,
            created_at="2025-01-15T10:00:00Z",
            last_activity="2025-01-15T14:30:00Z",
            expires_at="2025-01-22T10:00:00Z",
            is_current=is_current,
        )

    async def test_list_sessions_success(
        self,
        app_client: QuartTestClient,
        mock_session_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test successful session listing."""
        # Arrange
        user_id = "user-456"
        current_jti = "current-session-jti"
        mock_token_issuer.verify.return_value = {
            "sub": user_id,
            "jti": current_jti,
        }

        test_sessions = [
            self._create_test_session_info(jti=current_jti, is_current=True),
            self._create_test_session_info(jti="other-session", device_name="Firefox"),
        ]
        session_result = SessionListResult(test_sessions)
        mock_session_handler.list_user_sessions.return_value = session_result

        # Act
        response = await app_client.get(
            "/v1/auth/sessions",
            headers={"Authorization": "Bearer valid-jwt-token"},
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["total_count"] == 2
        assert len(data["sessions"]) == 2
        assert data["sessions"][0]["session_id"] == current_jti
        assert data["sessions"][0]["is_current"] is True

        # Verify handler was called with correct parameters
        mock_session_handler.list_user_sessions.assert_called_once()
        call_args = mock_session_handler.list_user_sessions.call_args
        assert call_args.kwargs["user_id"] == user_id
        assert call_args.kwargs["current_jti"] == current_jti
        assert "correlation_id" in call_args.kwargs

        # Verify token verification
        mock_token_issuer.verify.assert_called_once_with("valid-jwt-token")

    async def test_list_sessions_swedish_user_id(
        self,
        app_client: QuartTestClient,
        mock_session_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test session listing with Swedish characters in user context."""
        # Arrange - UUID can contain Swedish chars in metadata, not the UUID itself
        user_id = "åsa-öberg-user-id-123"
        mock_token_issuer.verify.return_value = {
            "sub": user_id,
            "jti": "test-jti",
        }

        test_sessions = [
            self._create_test_session_info(
                device_name="Åsa's Safari",
                ip_address="192.168.1.100",
            )
        ]
        session_result = SessionListResult(test_sessions)
        mock_session_handler.list_user_sessions.return_value = session_result

        # Act
        response = await app_client.get(
            "/v1/auth/sessions",
            headers={"Authorization": "Bearer valid-jwt-token"},
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["sessions"][0]["device_name"] == "Åsa's Safari"

        # Verify handler was called with Swedish user ID
        mock_session_handler.list_user_sessions.assert_called_once()
        call_args = mock_session_handler.list_user_sessions.call_args
        assert call_args.kwargs["user_id"] == user_id

    async def test_list_sessions_invalid_jwt(
        self,
        app_client: QuartTestClient,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test session listing with invalid JWT token."""
        # Arrange
        mock_token_issuer.verify.side_effect = Exception("Invalid token")

        # Act
        response = await app_client.get(
            "/v1/auth/sessions",
            headers={"Authorization": "Bearer invalid-token"},
        )

        # Assert
        assert response.status_code == 401
        data = await response.get_json()
        assert data["error"] == "Invalid or expired token"

    async def test_list_sessions_no_token(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test session listing without authorization token."""
        # Act
        response = await app_client.get("/v1/auth/sessions")

        # Assert
        assert response.status_code == 401
        data = await response.get_json()
        assert data["error"] == "Invalid or expired token"

    async def test_list_sessions_handler_error(
        self,
        app_client: QuartTestClient,
        mock_session_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test session listing with handler error."""
        # Arrange
        user_id = "user-123"
        mock_token_issuer.verify.return_value = {"sub": user_id, "jti": "test-jti"}

        correlation_id = str(uuid4())
        error_detail = create_test_error_detail(
            message="Session repository unavailable",
            correlation_id=correlation_id,
            operation="list_user_sessions",
            service="identity_service",
            details={"user_id": user_id},
        )
        huleedu_error = HuleEduError(error_detail)
        mock_session_handler.list_user_sessions.side_effect = huleedu_error

        # Act
        response = await app_client.get(
            "/v1/auth/sessions",
            headers={"Authorization": "Bearer valid-token"},
        )

        # Assert
        assert response.status_code == 400
        data = await response.get_json()
        error_response = data["error"]
        assert "Session repository unavailable" in error_response["message"]
        assert error_response["details"]["user_id"] == user_id

    async def test_revoke_session_success(
        self,
        app_client: QuartTestClient,
        mock_session_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test successful session revocation."""
        # Arrange
        user_id = "user-456"
        session_id = "session-to-revoke-123"
        mock_token_issuer.verify.return_value = {"sub": user_id, "jti": "current-jti"}

        revoke_result = SessionActionResult("Session revoked successfully", 1)
        mock_session_handler.revoke_session.return_value = revoke_result

        # Act
        response = await app_client.delete(
            f"/v1/auth/sessions/{session_id}",
            headers={"Authorization": "Bearer valid-token"},
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["message"] == "Session revoked successfully"
        assert data["sessions_affected"] == 1

        # Verify handler was called with correct parameters
        mock_session_handler.revoke_session.assert_called_once()
        call_args = mock_session_handler.revoke_session.call_args
        assert call_args.kwargs["user_id"] == user_id
        assert call_args.kwargs["session_id"] == session_id
        assert "correlation_id" in call_args.kwargs
        assert "ip_address" in call_args.kwargs

    async def test_revoke_session_not_found(
        self,
        app_client: QuartTestClient,
        mock_session_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test session revocation when session not found."""
        # Arrange
        user_id = "user-456"
        session_id = "non-existent-session"
        mock_token_issuer.verify.return_value = {"sub": user_id, "jti": "current-jti"}

        correlation_id = str(uuid4())
        error_detail = create_test_error_detail(
            message="Session not found or already revoked",
            correlation_id=correlation_id,
            operation="revoke_session",
            service="identity_service",
            details={"session_id": session_id, "user_id": user_id},
        )
        huleedu_error = HuleEduError(error_detail)
        mock_session_handler.revoke_session.side_effect = huleedu_error

        # Act
        response = await app_client.delete(
            f"/v1/auth/sessions/{session_id}",
            headers={"Authorization": "Bearer valid-token"},
        )

        # Assert
        assert response.status_code == 400
        data = await response.get_json()
        error_response = data["error"]
        assert "Session not found or already revoked" in error_response["message"]
        assert error_response["details"]["session_id"] == session_id

    async def test_revoke_all_sessions_success_exclude_current(
        self,
        app_client: QuartTestClient,
        mock_session_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test successful revocation of all sessions excluding current."""
        # Arrange
        user_id = "user-456"
        current_jti = "current-session-jti"
        mock_token_issuer.verify.return_value = {"sub": user_id, "jti": current_jti}

        revoke_result = SessionActionResult("All other sessions revoked", 3)
        mock_session_handler.revoke_all_sessions.return_value = revoke_result

        request_data = {"exclude_current": True}

        # Act
        response = await app_client.delete(
            "/v1/auth/sessions",
            json=request_data,
            headers={"Authorization": "Bearer valid-token"},
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["message"] == "All other sessions revoked"
        assert data["sessions_affected"] == 3

        # Verify handler was called with correct parameters
        mock_session_handler.revoke_all_sessions.assert_called_once()
        call_args = mock_session_handler.revoke_all_sessions.call_args
        assert call_args.kwargs["user_id"] == user_id
        assert call_args.kwargs["exclude_current"] is True
        assert call_args.kwargs["current_jti"] == current_jti
        assert "correlation_id" in call_args.kwargs
        assert "ip_address" in call_args.kwargs

    async def test_revoke_all_sessions_include_current(
        self,
        app_client: QuartTestClient,
        mock_session_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test revocation of all sessions including current."""
        # Arrange
        user_id = "user-456"
        current_jti = "current-session-jti"
        mock_token_issuer.verify.return_value = {"sub": user_id, "jti": current_jti}

        revoke_result = SessionActionResult("All sessions revoked", 4)
        mock_session_handler.revoke_all_sessions.return_value = revoke_result

        request_data = {"exclude_current": False}

        # Act
        response = await app_client.delete(
            "/v1/auth/sessions",
            json=request_data,
            headers={"Authorization": "Bearer valid-token"},
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["sessions_affected"] == 4

        # Verify exclude_current was set to False
        call_args = mock_session_handler.revoke_all_sessions.call_args
        assert call_args.kwargs["exclude_current"] is False

    async def test_revoke_all_sessions_no_body(
        self,
        app_client: QuartTestClient,
        mock_session_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test revocation of all sessions with no request body (defaults to exclude current)."""
        # Arrange
        user_id = "user-456"
        current_jti = "current-session-jti"
        mock_token_issuer.verify.return_value = {"sub": user_id, "jti": current_jti}

        revoke_result = SessionActionResult("Other sessions revoked", 2)
        mock_session_handler.revoke_all_sessions.return_value = revoke_result

        # Act
        response = await app_client.delete(
            "/v1/auth/sessions",
            headers={"Authorization": "Bearer valid-token"},
        )

        # Assert
        assert response.status_code == 200

        # Verify exclude_current defaults to True
        call_args = mock_session_handler.revoke_all_sessions.call_args
        assert call_args.kwargs["exclude_current"] is True

    async def test_get_active_session_count_success(
        self,
        app_client: QuartTestClient,
        mock_session_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test successful active session count retrieval."""
        # Arrange
        user_id = "user-456"
        mock_token_issuer.verify.return_value = {"sub": user_id, "jti": "current-jti"}

        count_result = ActiveSessionCountResult(5)
        mock_session_handler.get_active_session_count.return_value = count_result

        # Act
        response = await app_client.get(
            "/v1/auth/sessions/active",
            headers={"Authorization": "Bearer valid-token"},
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["active_sessions"] == 5

        # Verify handler was called with correct parameters
        mock_session_handler.get_active_session_count.assert_called_once()
        call_args = mock_session_handler.get_active_session_count.call_args
        assert call_args.kwargs["user_id"] == user_id
        assert "correlation_id" in call_args.kwargs

    async def test_get_active_session_count_invalid_token(
        self,
        app_client: QuartTestClient,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test active session count with invalid token."""
        # Arrange
        mock_token_issuer.verify.side_effect = Exception("Token expired")

        # Act
        response = await app_client.get(
            "/v1/auth/sessions/active",
            headers={"Authorization": "Bearer expired-token"},
        )

        # Assert
        assert response.status_code == 401
        data = await response.get_json()
        assert data["error"] == "Invalid or expired token"

    async def test_correlation_id_handling(
        self,
        app_client: QuartTestClient,
        mock_session_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test proper correlation ID handling in endpoints."""
        # Arrange
        user_id = "user-456"
        correlation_id = "12345678-1234-5678-9abc-123456789abc"
        mock_token_issuer.verify.return_value = {"sub": user_id, "jti": "test-jti"}

        count_result = ActiveSessionCountResult(3)
        mock_session_handler.get_active_session_count.return_value = count_result

        # Act
        response = await app_client.get(
            "/v1/auth/sessions/active",
            headers={
                "Authorization": "Bearer valid-token",
                "X-Correlation-ID": correlation_id,
            },
        )

        # Assert
        assert response.status_code == 200

        # Verify correlation ID was passed to handler
        call_args = mock_session_handler.get_active_session_count.call_args
        # The correlation_id in the call should match what we sent
        assert str(call_args.kwargs["correlation_id"]) == correlation_id

    async def test_unexpected_error_handling(
        self,
        app_client: QuartTestClient,
        mock_session_handler: AsyncMock,
        mock_token_issuer: AsyncMock,
    ) -> None:
        """Test handling of unexpected errors."""
        # Arrange
        user_id = "user-456"
        mock_token_issuer.verify.return_value = {"sub": user_id, "jti": "test-jti"}
        mock_session_handler.get_active_session_count.side_effect = Exception(
            "Database connection failed"
        )

        # Act
        response = await app_client.get(
            "/v1/auth/sessions/active",
            headers={"Authorization": "Bearer valid-token"},
        )

        # Assert
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Internal server error"
