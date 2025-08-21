"""
Unit tests for SessionManagementHandler domain logic behavior.

Tests focus on business logic and behavior rather than implementation details.
Uses protocol-based mocking following established patterns.
Swedish character support included for device information.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from services.identity_service.domain_handlers.session_management_handler import (
    ActiveSessionCountResult,
    SessionActionResult,
    SessionListResult,
    SessionManagementHandler,
)
from services.identity_service.protocols import (
    AuditLoggerProtocol,
    UserSessionRepositoryProtocol,
)


# Module-level fixtures for all test classes
@pytest.fixture
def mock_user_session_repo() -> AsyncMock:
    """Create mock user session repository following protocol."""
    return AsyncMock(spec=UserSessionRepositoryProtocol)


@pytest.fixture
def mock_audit_logger() -> AsyncMock:
    """Create mock audit logger following protocol."""
    return AsyncMock(spec=AuditLoggerProtocol)


@pytest.fixture
def handler(
    mock_user_session_repo: AsyncMock,
    mock_audit_logger: AsyncMock,
) -> SessionManagementHandler:
    """Create handler with all mocked dependencies."""
    return SessionManagementHandler(
        user_session_repo=mock_user_session_repo,
        audit_logger=mock_audit_logger,
    )


@pytest.fixture
def sample_user_id() -> str:
    """Generate sample user ID for testing."""
    return str(uuid4())


@pytest.fixture
def sample_correlation_id() -> UUID:
    """Generate sample correlation ID for testing."""
    return uuid4()


@pytest.fixture
def sample_session_data() -> list[dict]:
    """Create sample session data with Swedish characters."""
    return [
        {
            "jti": "session-1",
            "device_name": "Erik's MacBook",
            "device_type": "laptop",
            "ip_address": "192.168.1.100",
            "created_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            "last_activity": datetime(2024, 1, 15, 15, 30, 0, tzinfo=UTC),
            "expires_at": datetime(2024, 1, 22, 10, 0, 0, tzinfo=UTC),
            "user_id": uuid4(),
        },
        {
            "jti": "session-2",
            "device_name": "Åsa's iPhone",
            "device_type": "mobile",
            "ip_address": "192.168.1.101",
            "created_at": datetime(2024, 1, 14, 9, 0, 0, tzinfo=UTC),
            "last_activity": datetime(2024, 1, 15, 14, 0, 0, tzinfo=UTC),
            "expires_at": datetime(2024, 1, 21, 9, 0, 0, tzinfo=UTC),
            "user_id": uuid4(),
        },
    ]


class TestListUserSessions:
    """Tests for list_user_sessions method."""

    async def test_list_user_sessions_success(
        self,
        handler: SessionManagementHandler,
        mock_user_session_repo: AsyncMock,
        sample_user_id: str,
        sample_correlation_id: UUID,
        sample_session_data: list[dict],
    ) -> None:
        """Test successful session listing with sorted results."""
        # Arrange
        mock_user_session_repo.get_user_sessions.return_value = sample_session_data
        current_jti = "session-1"

        # Act
        result = await handler.list_user_sessions(
            user_id=sample_user_id,
            current_jti=current_jti,
            correlation_id=sample_correlation_id,
        )

        # Assert
        assert isinstance(result, SessionListResult)
        assert len(result.sessions) == 2

        # Verify sessions are sorted by creation date (newest first)
        assert result.sessions[0].jti == "session-1"
        assert result.sessions[1].jti == "session-2"

        # Verify current session is marked correctly
        assert result.sessions[0].is_current is True
        assert result.sessions[1].is_current is False

        # Verify Swedish characters are preserved
        assert result.sessions[1].device_name == "Åsa's iPhone"

        # Verify repository call
        mock_user_session_repo.get_user_sessions.assert_called_once_with(UUID(sample_user_id))

    async def test_list_user_sessions_no_current_jti(
        self,
        handler: SessionManagementHandler,
        mock_user_session_repo: AsyncMock,
        sample_user_id: str,
        sample_correlation_id: UUID,
        sample_session_data: list[dict],
    ) -> None:
        """Test session listing without current session identification."""
        # Arrange
        mock_user_session_repo.get_user_sessions.return_value = sample_session_data

        # Act
        result = await handler.list_user_sessions(
            user_id=sample_user_id,
            current_jti=None,
            correlation_id=sample_correlation_id,
        )

        # Assert
        assert isinstance(result, SessionListResult)
        assert len(result.sessions) == 2

        # Verify no session is marked as current
        assert all(not session.is_current for session in result.sessions)

    async def test_list_user_sessions_empty_result(
        self,
        handler: SessionManagementHandler,
        mock_user_session_repo: AsyncMock,
        sample_user_id: str,
        sample_correlation_id: UUID,
    ) -> None:
        """Test session listing with no active sessions."""
        # Arrange
        mock_user_session_repo.get_user_sessions.return_value = []

        # Act
        result = await handler.list_user_sessions(
            user_id=sample_user_id,
            current_jti=None,
            correlation_id=sample_correlation_id,
        )

        # Assert
        assert isinstance(result, SessionListResult)
        assert len(result.sessions) == 0

    async def test_list_user_sessions_invalid_user_id(
        self,
        handler: SessionManagementHandler,
        mock_user_session_repo: AsyncMock,
        sample_correlation_id: UUID,
    ) -> None:
        """Test session listing with invalid user ID format."""
        # Act & Assert
        with pytest.raises(ValueError):
            await handler.list_user_sessions(
                user_id="invalid-uuid",
                current_jti=None,
                correlation_id=sample_correlation_id,
            )


class TestRevokeSession:
    """Tests for revoke_session method."""

    async def test_revoke_session_success(
        self,
        handler: SessionManagementHandler,
        mock_user_session_repo: AsyncMock,
        mock_audit_logger: AsyncMock,
        sample_user_id: str,
        sample_correlation_id: UUID,
    ) -> None:
        """Test successful session revocation with audit logging."""
        # Arrange
        session_id = "session-123"
        ip_address = "192.168.1.100"
        session_data = {
            "jti": session_id,
            "user_id": UUID(sample_user_id),
            "device_name": "Lars' MacBook Pro",
            "device_type": "laptop",
        }

        mock_user_session_repo.get_session.return_value = session_data
        mock_user_session_repo.revoke_session.return_value = True

        # Act
        result = await handler.revoke_session(
            user_id=sample_user_id,
            session_id=session_id,
            correlation_id=sample_correlation_id,
            ip_address=ip_address,
        )

        # Assert
        assert isinstance(result, SessionActionResult)
        assert result.message == "Session revoked successfully"
        assert result.sessions_affected == 1

        # Verify repository calls
        mock_user_session_repo.get_session.assert_called_once_with(session_id)
        mock_user_session_repo.revoke_session.assert_called_once_with(session_id)

        # Verify audit logging
        mock_audit_logger.log_action.assert_called_once_with(
            action="session_revoked",
            user_id=UUID(sample_user_id),
            details={
                "revoked_session_id": session_id,
                "device_name": "Lars' MacBook Pro",
                "device_type": "laptop",
            },
            ip_address=ip_address,
            user_agent=None,
            correlation_id=sample_correlation_id,
        )

    async def test_revoke_session_not_found(
        self,
        handler: SessionManagementHandler,
        mock_user_session_repo: AsyncMock,
        mock_audit_logger: AsyncMock,
        sample_user_id: str,
        sample_correlation_id: UUID,
    ) -> None:
        """Test session revocation when session doesn't exist."""
        # Arrange
        session_id = "nonexistent-session"
        mock_user_session_repo.get_session.return_value = None

        # Act
        result = await handler.revoke_session(
            user_id=sample_user_id,
            session_id=session_id,
            correlation_id=sample_correlation_id,
        )

        # Assert
        assert isinstance(result, SessionActionResult)
        assert result.message == "Session not found or already revoked"
        assert result.sessions_affected == 0

        # Verify no audit logging for non-existent session
        mock_audit_logger.log_action.assert_not_called()

    async def test_revoke_session_unauthorized(
        self,
        handler: SessionManagementHandler,
        mock_user_session_repo: AsyncMock,
        mock_audit_logger: AsyncMock,
        sample_user_id: str,
        sample_correlation_id: UUID,
    ) -> None:
        """Test session revocation when session belongs to different user."""
        # Arrange
        session_id = "session-123"
        ip_address = "192.168.1.100"
        other_user_id = str(uuid4())
        session_data = {
            "jti": session_id,
            "user_id": UUID(other_user_id),  # Different user
            "device_name": "Unauthorized Device",
            "device_type": "laptop",
        }

        mock_user_session_repo.get_session.return_value = session_data

        # Act
        result = await handler.revoke_session(
            user_id=sample_user_id,
            session_id=session_id,
            correlation_id=sample_correlation_id,
            ip_address=ip_address,
        )

        # Assert
        assert isinstance(result, SessionActionResult)
        assert result.message == "Session not found or already revoked"
        assert result.sessions_affected == 0

        # Verify unauthorized attempt is logged
        mock_audit_logger.log_action.assert_called_once_with(
            action="session_revoke_unauthorized",
            user_id=UUID(sample_user_id),
            details={
                "attempted_session_id": session_id,
                "session_owner_id": other_user_id,
            },
            ip_address=ip_address,
            user_agent=None,
            correlation_id=sample_correlation_id,
        )

    async def test_revoke_session_failed(
        self,
        handler: SessionManagementHandler,
        mock_user_session_repo: AsyncMock,
        mock_audit_logger: AsyncMock,
        sample_user_id: str,
        sample_correlation_id: UUID,
    ) -> None:
        """Test session revocation when revoke operation fails."""
        # Arrange
        session_id = "session-123"
        session_data = {
            "jti": session_id,
            "user_id": UUID(sample_user_id),
            "device_name": "Test Device",
            "device_type": "laptop",
        }

        mock_user_session_repo.get_session.return_value = session_data
        mock_user_session_repo.revoke_session.return_value = False

        # Act
        result = await handler.revoke_session(
            user_id=sample_user_id,
            session_id=session_id,
            correlation_id=sample_correlation_id,
        )

        # Assert
        assert isinstance(result, SessionActionResult)
        assert result.message == "Session not found or already revoked"
        assert result.sessions_affected == 0

        # Verify no audit logging for failed revocation
        mock_audit_logger.log_action.assert_not_called()


class TestRevokeAllSessions:
    """Tests for revoke_all_sessions method."""

    async def test_revoke_all_sessions_exclude_current(
        self,
        handler: SessionManagementHandler,
        mock_user_session_repo: AsyncMock,
        mock_audit_logger: AsyncMock,
        sample_user_id: str,
        sample_correlation_id: UUID,
        sample_session_data: list[dict],
    ) -> None:
        """Test revoking all sessions while excluding current session."""
        # Arrange
        current_jti = "session-1"
        ip_address = "192.168.1.100"

        mock_user_session_repo.get_user_sessions.return_value = sample_session_data
        mock_user_session_repo.revoke_session.return_value = True

        # Act
        result = await handler.revoke_all_sessions(
            user_id=sample_user_id,
            correlation_id=sample_correlation_id,
            exclude_current=True,
            current_jti=current_jti,
            ip_address=ip_address,
        )

        # Assert
        assert isinstance(result, SessionActionResult)
        assert "Successfully revoked 1 session(s)" in result.message
        assert "(excluding current session)" in result.message
        assert result.sessions_affected == 1

        # Verify only non-current session was revoked
        mock_user_session_repo.revoke_session.assert_called_once_with("session-2")

        # Verify audit logging
        mock_audit_logger.log_action.assert_called_once_with(
            action="all_sessions_revoked",
            user_id=UUID(sample_user_id),
            details={
                "sessions_revoked": 1,
                "excluded_current": True,
                "current_session": current_jti,
            },
            ip_address=ip_address,
            user_agent=None,
            correlation_id=sample_correlation_id,
        )

    async def test_revoke_all_sessions_include_current(
        self,
        handler: SessionManagementHandler,
        mock_user_session_repo: AsyncMock,
        mock_audit_logger: AsyncMock,
        sample_user_id: str,
        sample_correlation_id: UUID,
    ) -> None:
        """Test revoking all sessions including current session."""
        # Arrange
        revoked_count = 3
        mock_user_session_repo.revoke_all_user_sessions.return_value = revoked_count

        # Act
        result = await handler.revoke_all_sessions(
            user_id=sample_user_id,
            correlation_id=sample_correlation_id,
            exclude_current=False,
        )

        # Assert
        assert isinstance(result, SessionActionResult)
        assert result.message == "Successfully revoked 3 session(s)"
        assert "(excluding current session)" not in result.message
        assert result.sessions_affected == 3

        # Verify all sessions revoked
        mock_user_session_repo.revoke_all_user_sessions.assert_called_once_with(
            UUID(sample_user_id)
        )

        # Verify audit logging
        mock_audit_logger.log_action.assert_called_once_with(
            action="all_sessions_revoked",
            user_id=UUID(sample_user_id),
            details={
                "sessions_revoked": 3,
                "excluded_current": False,
                "current_session": None,
            },
            ip_address=None,
            user_agent=None,
            correlation_id=sample_correlation_id,
        )

    async def test_revoke_all_sessions_no_sessions(
        self,
        handler: SessionManagementHandler,
        mock_user_session_repo: AsyncMock,
        mock_audit_logger: AsyncMock,
        sample_user_id: str,
        sample_correlation_id: UUID,
    ) -> None:
        """Test revoking all sessions when user has no sessions."""
        # Arrange
        mock_user_session_repo.get_user_sessions.return_value = []

        # Act
        result = await handler.revoke_all_sessions(
            user_id=sample_user_id,
            correlation_id=sample_correlation_id,
            exclude_current=True,
            current_jti="current-session",
        )

        # Assert
        assert isinstance(result, SessionActionResult)
        assert result.message == "Successfully revoked 0 session(s) (excluding current session)"
        assert result.sessions_affected == 0


class TestGetActiveSessionCount:
    """Tests for get_active_session_count method."""

    async def test_get_active_session_count_success(
        self,
        handler: SessionManagementHandler,
        mock_user_session_repo: AsyncMock,
        sample_user_id: str,
        sample_correlation_id: UUID,
        sample_session_data: list[dict],
    ) -> None:
        """Test successful active session count retrieval."""
        # Arrange
        mock_user_session_repo.get_user_sessions.return_value = sample_session_data

        # Act
        result = await handler.get_active_session_count(
            user_id=sample_user_id,
            correlation_id=sample_correlation_id,
        )

        # Assert
        assert isinstance(result, ActiveSessionCountResult)
        assert result.active_sessions == 2

        # Verify repository call
        mock_user_session_repo.get_user_sessions.assert_called_once_with(UUID(sample_user_id))

    async def test_get_active_session_count_no_sessions(
        self,
        handler: SessionManagementHandler,
        mock_user_session_repo: AsyncMock,
        sample_user_id: str,
        sample_correlation_id: UUID,
    ) -> None:
        """Test session count when user has no active sessions."""
        # Arrange
        mock_user_session_repo.get_user_sessions.return_value = []

        # Act
        result = await handler.get_active_session_count(
            user_id=sample_user_id,
            correlation_id=sample_correlation_id,
        )

        # Assert
        assert isinstance(result, ActiveSessionCountResult)
        assert result.active_sessions == 0

    async def test_get_active_session_count_invalid_user_id(
        self,
        handler: SessionManagementHandler,
        mock_user_session_repo: AsyncMock,
        sample_correlation_id: UUID,
    ) -> None:
        """Test session count with invalid user ID format."""
        # Act & Assert
        with pytest.raises(ValueError):
            await handler.get_active_session_count(
                user_id="invalid-uuid",
                correlation_id=sample_correlation_id,
            )
