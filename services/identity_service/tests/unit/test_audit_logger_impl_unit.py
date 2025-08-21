"""
Unit tests for AuditLoggerImpl database-backed security audit logging.

Tests comprehensive audit logging functionality including security event tracking,
database session management, error resilience, and Swedish character handling.
Following Rule 075 test creation methodology with protocol-based DI patterns.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, call
from uuid import UUID, uuid4

import pytest
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.identity_service.implementations.audit_logger_impl import AuditLoggerImpl
from services.identity_service.models_db import AuditLog

# Test logger for debugging
logger = create_service_logger("test.audit_logger_impl")


class TestAuditLoggerImpl:
    """Tests for database-backed audit logger implementation."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock AsyncSession with proper spec."""
        from unittest.mock import MagicMock
        
        session = AsyncMock(spec=AsyncSession)
        # Mock the add and commit methods - add is sync, commit is async
        session.add = MagicMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def mock_session_factory(self, mock_session: AsyncMock) -> MagicMock:
        """Create a mock session factory that returns the mock session."""
        
        # Configure the session mock to be an async context manager
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        # Create the factory that returns the session when called - use MagicMock not AsyncMock
        factory = MagicMock()
        factory.return_value = mock_session
        return factory

    @pytest.fixture
    def audit_logger(self, mock_session_factory: MagicMock) -> AuditLoggerImpl:
        """Create AuditLoggerImpl instance with mocked session factory."""
        return AuditLoggerImpl(session_factory=mock_session_factory)

    @pytest.mark.parametrize(
        "action, user_id, details, ip_address, user_agent",
        [
            # Basic login success with Swedish email
            (
                "login_success",
                uuid4(),
                {"email": "maria.svensson@huledu.se"},
                "192.168.1.100",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            ),
            # Password change event
            (
                "password_change",
                uuid4(),
                {"event": "Password successfully changed"},
                "10.0.0.50",
                "Chrome/91.0.4472.124",
            ),
            # Token refresh with JTI prefix
            (
                "token_refresh",
                uuid4(),
                {"operation": "refresh", "jti_prefix": "abc12345"},
                "172.16.0.10",
                "Safari/14.1.1",
            ),
            # Anonymous action (no user_id)
            (
                "registration_attempt",
                None,
                {"email": "åsa.öström@skolan.se"},
                "203.0.113.45",
                None,
            ),
            # Complex details with Swedish characters
            (
                "profile_update",
                uuid4(),
                {"name": "Björn Åkesson", "locale": "sv-SE", "city": "Göteborg"},
                None,
                "Mobile Safari/604.1",
            ),
        ],
    )
    async def test_log_action_creates_audit_record(
        self,
        audit_logger: AuditLoggerImpl,
        mock_session_factory: MagicMock,
        mock_session: AsyncMock,
        action: str,
        user_id: UUID | None,
        details: dict[str, Any],
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        """Test that log_action creates audit record and persists to database."""
        correlation_id = uuid4()

        await audit_logger.log_action(
            action=action,
            user_id=user_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )

        # Verify session factory was called
        mock_session_factory.assert_called_once()
        
        # Verify session context manager was entered
        context_manager = mock_session_factory.return_value
        context_manager.__aenter__.assert_called_once()
        context_manager.__aexit__.assert_called_once()

        # Verify AuditLog was added to session
        mock_session.add.assert_called_once()
        added_audit_log = mock_session.add.call_args[0][0]
        
        # Verify AuditLog properties
        assert isinstance(added_audit_log, AuditLog)
        assert added_audit_log.action == action
        assert added_audit_log.user_id == user_id
        assert added_audit_log.details == details
        assert added_audit_log.ip_address == ip_address
        assert added_audit_log.user_agent == user_agent
        assert added_audit_log.correlation_id == correlation_id

        # Verify transaction was committed
        mock_session.commit.assert_called_once()

    async def test_log_action_handles_empty_details(
        self,
        audit_logger: AuditLoggerImpl,
        mock_session: AsyncMock,
        mock_session_factory: MagicMock,
    ) -> None:
        """Test log_action handles None details parameter correctly."""
        correlation_id = uuid4()

        await audit_logger.log_action(
            action="system_startup",
            user_id=None,
            details=None,
            ip_address=None,
            user_agent=None,
            correlation_id=correlation_id,
        )

        # Verify audit log was created with None details
        mock_session.add.assert_called_once()
        added_audit_log = mock_session.add.call_args[0][0]
        assert added_audit_log.details is None

    async def test_log_action_database_error_resilience(
        self,
        audit_logger: AuditLoggerImpl,
        mock_session_factory: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        """Test that database errors don't fail operations and audit logic continues."""
        # Configure session.commit to raise an exception
        mock_session.commit.side_effect = Exception("Database connection failed")
        
        correlation_id = uuid4()
        user_id = uuid4()

        # Operation should not raise exception despite database failure
        await audit_logger.log_action(
            action="login_attempt",
            user_id=user_id,
            details={"email": "test@huledu.se"},
            ip_address="192.168.1.1",
            user_agent="TestAgent",
            correlation_id=correlation_id,
        )

        # Verify audit log creation was attempted but failed gracefully
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        
        # Verify the audit log object was correctly created despite database failure
        added_audit_log = mock_session.add.call_args[0][0]
        assert isinstance(added_audit_log, AuditLog)
        assert added_audit_log.action == "login_attempt"
        assert added_audit_log.user_id == user_id

    @pytest.mark.parametrize(
        "email, success, user_id, failure_reason, expected_action, expected_details",
        [
            # Successful login with Swedish email
            (
                "anna.lindqvist@huledu.se",
                True,
                uuid4(),
                None,
                "login_success",
                {"email": "anna.lindqvist@huledu.se", "success": True},
            ),
            # Failed login with invalid password
            (
                "erik.johansson@skola.se",
                False,
                None,
                "invalid_password",
                "login_failure",
                {
                    "email": "erik.johansson@skola.se",
                    "success": False,
                    "failure_reason": "invalid_password",
                },
            ),
            # Failed login due to account lockout
            (
                "maja.ström@universitet.se",
                False,
                None,
                "account_locked",
                "login_failure",
                {
                    "email": "maja.ström@universitet.se",
                    "success": False,
                    "failure_reason": "account_locked",
                },
            ),
            # Successful login without failure reason
            (
                "lars.berg@gymnasiet.se",
                True,
                uuid4(),
                None,
                "login_success",
                {"email": "lars.berg@gymnasiet.se", "success": True},
            ),
        ],
    )
    async def test_log_login_attempt_delegates_correctly(
        self,
        audit_logger: AuditLoggerImpl,
        mock_session: AsyncMock,
        email: str,
        success: bool,
        user_id: UUID | None,
        failure_reason: str | None,
        expected_action: str,
        expected_details: dict[str, Any],
    ) -> None:
        """Test login attempt logging with proper action and details formatting."""
        correlation_id = uuid4()
        ip_address = "203.0.113.100"
        user_agent = "Mozilla/5.0 Test Browser"

        await audit_logger.log_login_attempt(
            email=email,
            success=success,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
            failure_reason=failure_reason,
        )

        # Verify audit log creation
        mock_session.add.assert_called_once()
        added_audit_log = mock_session.add.call_args[0][0]
        
        assert added_audit_log.action == expected_action
        assert added_audit_log.user_id == user_id
        assert added_audit_log.details == expected_details
        assert added_audit_log.ip_address == ip_address
        assert added_audit_log.user_agent == user_agent
        assert added_audit_log.correlation_id == correlation_id

    async def test_log_password_change_creates_correct_audit_event(
        self,
        audit_logger: AuditLoggerImpl,
        mock_session: AsyncMock,
    ) -> None:
        """Test password change logging with proper event details."""
        user_id = uuid4()
        correlation_id = uuid4()
        ip_address = "10.0.0.25"
        user_agent = "Chrome/96.0.4664.110"

        await audit_logger.log_password_change(
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )

        # Verify audit log properties
        mock_session.add.assert_called_once()
        added_audit_log = mock_session.add.call_args[0][0]
        
        assert added_audit_log.action == "password_change"
        assert added_audit_log.user_id == user_id
        assert added_audit_log.details == {"event": "Password successfully changed"}
        assert added_audit_log.ip_address == ip_address
        assert added_audit_log.user_agent == user_agent
        assert added_audit_log.correlation_id == correlation_id

    @pytest.mark.parametrize(
        "operation, jti, expected_action, expected_jti_prefix",
        [
            # Token refresh with full JTI
            ("refresh", "abcdef123456789", "token_refresh", "abcdef12"),
            # Token revoke with short JTI
            ("revoke", "xyz789", "token_revoke", "xyz789"),
            # Token issue with exactly 8 chars
            ("issue", "12345678", "token_issue", "12345678"),
            # Token operation with very long JTI
            ("refresh", "verylongjtithatexceeds8characters", "token_refresh", "verylong"),
            # Token operation without JTI
            ("logout", None, "token_logout", None),
        ],
    )
    async def test_log_token_operation_handles_jti_security(
        self,
        audit_logger: AuditLoggerImpl,
        mock_session: AsyncMock,
        operation: str,
        jti: str | None,
        expected_action: str,
        expected_jti_prefix: str | None,
    ) -> None:
        """Test token operation logging with proper JTI prefix handling for security."""
        user_id = uuid4()
        correlation_id = uuid4()
        ip_address = "172.16.10.50"
        user_agent = "Safari/15.1"

        await audit_logger.log_token_operation(
            operation=operation,
            user_id=user_id,
            jti=jti,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )

        # Verify audit log creation
        mock_session.add.assert_called_once()
        added_audit_log = mock_session.add.call_args[0][0]
        
        assert added_audit_log.action == expected_action
        assert added_audit_log.user_id == user_id
        assert added_audit_log.ip_address == ip_address
        assert added_audit_log.user_agent == user_agent
        assert added_audit_log.correlation_id == correlation_id
        
        # Verify details structure and JTI handling
        expected_details = {"operation": operation}
        if expected_jti_prefix:
            expected_details["jti_prefix"] = expected_jti_prefix
            
        assert added_audit_log.details == expected_details

    async def test_log_token_operation_without_jti(
        self,
        audit_logger: AuditLoggerImpl,
        mock_session: AsyncMock,
    ) -> None:
        """Test token operation logging when JTI is None."""
        user_id = uuid4()
        correlation_id = uuid4()

        await audit_logger.log_token_operation(
            operation="logout",
            user_id=user_id,
            jti=None,
            ip_address="192.168.1.200",
            user_agent="Mobile Browser",
            correlation_id=correlation_id,
        )

        # Verify audit log details don't include jti_prefix when JTI is None
        mock_session.add.assert_called_once()
        added_audit_log = mock_session.add.call_args[0][0]
        
        assert added_audit_log.details == {"operation": "logout"}
        assert "jti_prefix" not in added_audit_log.details

    async def test_session_factory_exception_handling(
        self,
        mock_session_factory: MagicMock,
    ) -> None:
        """Test resilience when session factory itself fails."""
        # Configure session factory to raise exception
        mock_session_factory.side_effect = Exception("Session factory initialization failed")
        
        audit_logger = AuditLoggerImpl(session_factory=mock_session_factory)
        correlation_id = uuid4()

        # Operation should not raise exception despite session factory failure
        await audit_logger.log_action(
            action="test_action",
            user_id=uuid4(),
            details={"test": "data"},
            ip_address="127.0.0.1",
            user_agent="TestAgent",
            correlation_id=correlation_id,
        )

        # Verify session factory was called (showing the attempt was made)
        mock_session_factory.assert_called_once()

    @pytest.mark.parametrize(
        "test_scenario",
        [
            # Swedish characters in email and details
            {
                "email": "åsa.ström@högskolanväst.se",
                "details": {"namn": "Åsa Ström", "stad": "Göteborg"},
                "description": "Swedish characters in email and name fields",
            },
            # Unicode normalization test
            {
                "email": "björn@skolan.se",
                "details": {"message": "Förändring av lösenord"},
                "description": "Swedish special characters requiring proper encoding",
            },
        ],
    )
    async def test_swedish_character_handling(
        self,
        audit_logger: AuditLoggerImpl,
        mock_session: AsyncMock,
        test_scenario: dict[str, Any],
    ) -> None:
        """Test proper handling of Swedish characters in audit logs."""
        correlation_id = uuid4()

        await audit_logger.log_login_attempt(
            email=test_scenario["email"],
            success=True,
            user_id=uuid4(),
            ip_address="192.168.1.1",
            user_agent="Swedish Browser",
            correlation_id=correlation_id,
        )

        # Verify Swedish characters are preserved in audit log
        mock_session.add.assert_called_once()
        added_audit_log = mock_session.add.call_args[0][0]
        
        # Verify email in details contains Swedish characters
        assert test_scenario["email"] in str(added_audit_log.details)
        assert added_audit_log.details["email"] == test_scenario["email"]

    async def test_multiple_audit_operations_session_isolation(
        self,
        audit_logger: AuditLoggerImpl,
        mock_session_factory: MagicMock,
    ) -> None:
        """Test that multiple audit operations use separate sessions."""
        correlation_id = uuid4()
        user_id = uuid4()

        # Perform multiple operations
        await audit_logger.log_login_attempt(
            email="user1@huledu.se",
            success=True,
            user_id=user_id,
            ip_address="192.168.1.1",
            user_agent="Browser1",
            correlation_id=correlation_id,
        )

        await audit_logger.log_password_change(
            user_id=user_id,
            ip_address="192.168.1.1",
            user_agent="Browser1",
            correlation_id=correlation_id,
        )

        await audit_logger.log_token_operation(
            operation="refresh",
            user_id=user_id,
            jti="testjti123",
            ip_address="192.168.1.1",
            user_agent="Browser1",
            correlation_id=correlation_id,
        )

        # Verify session factory was called three times (one per operation)
        assert mock_session_factory.call_count == 3

    async def test_correlation_id_consistency(
        self,
        audit_logger: AuditLoggerImpl,
        mock_session: AsyncMock,
    ) -> None:
        """Test that correlation IDs are properly tracked across audit operations."""
        correlation_id = uuid4()
        user_id = uuid4()

        # Perform login attempt
        await audit_logger.log_login_attempt(
            email="user@huledu.se",
            success=True,
            user_id=user_id,
            ip_address="192.168.1.1",
            user_agent="TestBrowser",
            correlation_id=correlation_id,
        )

        # Verify correlation ID is preserved
        mock_session.add.assert_called_once()
        added_audit_log = mock_session.add.call_args[0][0]
        assert added_audit_log.correlation_id == correlation_id