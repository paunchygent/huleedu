"""
Unit tests for PasswordResetHandler domain logic behavior.

Tests focus on business logic and behavior rather than implementation details.
Uses protocol-based mocking following established patterns.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from huleedu_service_libs.error_handling import HuleEduError

from services.identity_service.api.schemas import (
    RequestPasswordResetRequest,
    RequestPasswordResetResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
)
from services.identity_service.domain_handlers.password_reset_handler import (
    PasswordResetHandler,
    RequestPasswordResetResult,
    ResetPasswordResult,
)
from services.identity_service.protocols import (
    AuditLoggerProtocol,
    IdentityEventPublisherProtocol,
    PasswordHasher,
    UserRepo,
)


class TestPasswordResetHandler:
    """Tests for PasswordResetHandler business logic behavior."""

    @pytest.fixture
    def mock_user_repo(self) -> AsyncMock:
        """Create mock user repository following protocol."""
        return AsyncMock(spec=UserRepo)

    @pytest.fixture
    def mock_password_hasher(self) -> AsyncMock:
        """Create mock password hasher following protocol."""
        return AsyncMock(spec=PasswordHasher)

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher following protocol."""
        return AsyncMock(spec=IdentityEventPublisherProtocol)

    @pytest.fixture
    def mock_audit_logger(self) -> AsyncMock:
        """Create mock audit logger following protocol."""
        return AsyncMock(spec=AuditLoggerProtocol)

    @pytest.fixture
    def handler(
        self,
        mock_user_repo: AsyncMock,
        mock_password_hasher: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_audit_logger: AsyncMock,
    ) -> PasswordResetHandler:
        """Create handler with mocked dependencies."""
        return PasswordResetHandler(
            user_repo=mock_user_repo,
            password_hasher=mock_password_hasher,
            event_publisher=mock_event_publisher,
            audit_logger=mock_audit_logger,
        )

    @pytest.fixture
    def correlation_id(self) -> UUID:
        """Sample correlation ID for testing."""
        return uuid4()

    @pytest.fixture
    def sample_user_dict(self) -> dict:
        """Create sample user dict as returned by repository."""
        return {
            "id": str(uuid4()),
            "email": "test@example.com",
            "password_hash": "existing_hash",
        }

    @pytest.fixture
    def sample_token_record(self) -> dict:
        """Create sample password reset token record."""
        token_id = str(uuid4())
        user_id = str(uuid4())
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        return {
            "id": token_id,
            "user_id": user_id,
            "token": str(uuid4()),
            "expires_at": expires_at,
            "used_at": None,
        }

    class TestRequestPasswordReset:
        """Tests for request_password_reset method behavior."""

        @pytest.fixture
        def valid_reset_request(self) -> RequestPasswordResetRequest:
            """Create valid password reset request."""
            return RequestPasswordResetRequest(email="test@example.com")

        @pytest.fixture
        def swedish_reset_request(self) -> RequestPasswordResetRequest:
            """Create password reset request with Swedish email."""
            return RequestPasswordResetRequest(email="åsa.öberg@skolan.se")

        async def test_successful_reset_request_for_existing_user(
            self,
            handler: PasswordResetHandler,
            mock_user_repo: AsyncMock,
            mock_event_publisher: AsyncMock,
            mock_audit_logger: AsyncMock,
            valid_reset_request: RequestPasswordResetRequest,
            correlation_id: UUID,
            sample_user_dict: dict,
        ) -> None:
            """Should successfully request password reset for existing user."""
            # Setup: existing user found, successful token creation
            token_record = {
                "id": str(uuid4()),
                "user_id": sample_user_dict["id"],
                "token": str(uuid4()),
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
            }

            mock_user_repo.get_user_by_email.return_value = sample_user_dict
            mock_user_repo.invalidate_password_reset_tokens.return_value = None
            mock_user_repo.create_password_reset_token.return_value = token_record

            result = await handler.request_password_reset(
                valid_reset_request, correlation_id, ip_address="192.168.1.1"
            )

            # Verify return value (security: generic success message)
            assert isinstance(result, RequestPasswordResetResult)
            assert isinstance(result.response, RequestPasswordResetResponse)
            assert "email address exists" in result.response.message
            assert result.response.correlation_id == str(correlation_id)

            # Verify repository interactions
            mock_user_repo.get_user_by_email.assert_called_once_with(valid_reset_request.email)
            mock_user_repo.invalidate_password_reset_tokens.assert_called_once_with(
                sample_user_dict["id"]
            )
            mock_user_repo.create_password_reset_token.assert_called_once()

            # Verify token creation with proper expiry
            create_args = mock_user_repo.create_password_reset_token.call_args[0]
            assert create_args[0] == sample_user_dict["id"]  # user_id
            assert isinstance(create_args[1], str)  # token is UUID string
            assert isinstance(create_args[2], datetime)  # expires_at is datetime

            # Verify event publishing
            mock_event_publisher.publish_password_reset_requested.assert_called_once()
            publish_args = mock_event_publisher.publish_password_reset_requested.call_args[0]
            assert publish_args[0] == sample_user_dict
            assert publish_args[1] == token_record["id"]
            assert isinstance(publish_args[2], datetime)  # expires_at is datetime
            assert publish_args[3] == str(correlation_id)

            # Verify audit logging
            mock_audit_logger.log_action.assert_called_once()
            audit_call = mock_audit_logger.log_action.call_args
            assert audit_call[1]["action"] == "password_reset_requested"
            assert audit_call[1]["user_id"] == UUID(sample_user_dict["id"])
            assert audit_call[1]["details"]["email"] == sample_user_dict["email"]
            assert audit_call[1]["details"]["token_id"] == token_record["id"]
            assert "expires_at" in audit_call[1]["details"]
            assert audit_call[1]["ip_address"] == "192.168.1.1"
            assert audit_call[1]["user_agent"] is None
            assert audit_call[1]["correlation_id"] == correlation_id

        async def test_reset_request_for_nonexistent_user_succeeds(
            self,
            handler: PasswordResetHandler,
            mock_user_repo: AsyncMock,
            mock_event_publisher: AsyncMock,
            mock_audit_logger: AsyncMock,
            valid_reset_request: RequestPasswordResetRequest,
            correlation_id: UUID,
        ) -> None:
            """Should succeed for non-existent user (security: email non-disclosure)."""
            # Setup: no user found
            mock_user_repo.get_user_by_email.return_value = None

            result = await handler.request_password_reset(
                valid_reset_request, correlation_id, ip_address="192.168.1.1"
            )

            # Verify generic success response (security best practice)
            assert isinstance(result, RequestPasswordResetResult)
            assert "email address exists" in result.response.message
            assert result.response.correlation_id == str(correlation_id)

            # Verify no token operations performed
            mock_user_repo.invalidate_password_reset_tokens.assert_not_called()
            mock_user_repo.create_password_reset_token.assert_not_called()
            mock_event_publisher.publish_password_reset_requested.assert_not_called()

            # Verify security audit log for non-existent email
            mock_audit_logger.log_action.assert_called_once_with(
                action="password_reset_requested_nonexistent",
                user_id=None,
                details={"email": valid_reset_request.email},
                ip_address="192.168.1.1",
                user_agent=None,
                correlation_id=correlation_id,
            )

        async def test_reset_request_with_swedish_email(
            self,
            handler: PasswordResetHandler,
            mock_user_repo: AsyncMock,
            mock_event_publisher: AsyncMock,
            mock_audit_logger: AsyncMock,
            swedish_reset_request: RequestPasswordResetRequest,
            correlation_id: UUID,
        ) -> None:
            """Should handle Swedish characters in email addresses correctly."""
            swedish_user_dict = {
                "id": str(uuid4()),
                "email": "åsa.öberg@skolan.se",
                "password_hash": "existing_hash",
            }

            token_record = {
                "id": str(uuid4()),
                "user_id": swedish_user_dict["id"],
                "token": str(uuid4()),
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
            }

            mock_user_repo.get_user_by_email.return_value = swedish_user_dict
            mock_user_repo.invalidate_password_reset_tokens.return_value = None
            mock_user_repo.create_password_reset_token.return_value = token_record

            result = await handler.request_password_reset(swedish_reset_request, correlation_id)

            assert isinstance(result, RequestPasswordResetResult)

            # Verify Swedish email passed correctly to repository
            mock_user_repo.get_user_by_email.assert_called_once_with("åsa.öberg@skolan.se")

            # Verify audit log contains Swedish email
            audit_call = mock_audit_logger.log_action.call_args
            assert audit_call[1]["details"]["email"] == "åsa.öberg@skolan.se"

        async def test_token_expiration_is_one_hour(
            self,
            handler: PasswordResetHandler,
            mock_user_repo: AsyncMock,
            mock_event_publisher: AsyncMock,
            mock_audit_logger: AsyncMock,
            valid_reset_request: RequestPasswordResetRequest,
            correlation_id: UUID,
            sample_user_dict: dict,
        ) -> None:
            """Should set token expiry to exactly 1 hour for security."""
            token_record = {
                "id": str(uuid4()),
                "user_id": sample_user_dict["id"],
                "token": str(uuid4()),
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
            }

            mock_user_repo.get_user_by_email.return_value = sample_user_dict
            mock_user_repo.create_password_reset_token.return_value = token_record

            await handler.request_password_reset(valid_reset_request, correlation_id)

            # Verify token expiry is approximately 1 hour
            create_args = mock_user_repo.create_password_reset_token.call_args[0]
            expires_at = create_args[2]
            now = datetime.now(UTC)
            time_diff = expires_at - now
            # Allow small variance for test execution time
            assert timedelta(minutes=59) <= time_diff <= timedelta(minutes=61)

    class TestResetPassword:
        """Tests for reset_password method behavior."""

        @pytest.fixture
        def valid_reset_password_request(self) -> ResetPasswordRequest:
            """Create valid reset password request."""
            return ResetPasswordRequest(
                token=str(uuid4()),
                new_password="NewSecurePass123!",
            )

        @pytest.fixture
        def swedish_reset_password_request(self) -> ResetPasswordRequest:
            """Create reset password request with Swedish password."""
            return ResetPasswordRequest(
                token=str(uuid4()),
                new_password="Lösenord123!",
            )

        async def test_successful_password_reset(
            self,
            handler: PasswordResetHandler,
            mock_user_repo: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_event_publisher: AsyncMock,
            mock_audit_logger: AsyncMock,
            valid_reset_password_request: ResetPasswordRequest,
            correlation_id: UUID,
            sample_user_dict: dict,
            sample_token_record: dict,
        ) -> None:
            """Should successfully reset password with valid token."""
            # Setup: valid token and user found
            mock_user_repo.get_password_reset_token.return_value = sample_token_record
            mock_user_repo.get_user_by_id.return_value = sample_user_dict
            mock_password_hasher.hash.return_value = "new_hashed_password"

            result = await handler.reset_password(
                valid_reset_password_request, correlation_id, ip_address="192.168.1.1"
            )

            # Verify return value
            assert isinstance(result, ResetPasswordResult)
            assert isinstance(result.response, ResetPasswordResponse)
            assert result.response.message == "Password reset successfully"

            # Verify password hashing
            mock_password_hasher.hash.assert_called_once_with(
                valid_reset_password_request.new_password
            )

            # Verify password update and token marking
            mock_user_repo.update_user_password.assert_called_once_with(
                sample_user_dict["id"], "new_hashed_password"
            )
            mock_user_repo.mark_reset_token_used.assert_called_once_with(sample_token_record["id"])

            # Verify event publishing
            mock_event_publisher.publish_password_reset_completed.assert_called_once_with(
                sample_user_dict, str(correlation_id)
            )

            # Verify audit logging
            mock_audit_logger.log_action.assert_called_once_with(
                action="password_reset_completed",
                user_id=UUID(sample_user_dict["id"]),
                details={"email": sample_user_dict["email"], "token_id": sample_token_record["id"]},
                ip_address="192.168.1.1",
                user_agent=None,
                correlation_id=correlation_id,
            )

        async def test_reset_password_with_swedish_characters(
            self,
            handler: PasswordResetHandler,
            mock_user_repo: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_event_publisher: AsyncMock,
            mock_audit_logger: AsyncMock,
            swedish_reset_password_request: ResetPasswordRequest,
            correlation_id: UUID,
            sample_user_dict: dict,
            sample_token_record: dict,
        ) -> None:
            """Should handle Swedish characters in passwords correctly."""
            mock_user_repo.get_password_reset_token.return_value = sample_token_record
            mock_user_repo.get_user_by_id.return_value = sample_user_dict
            mock_password_hasher.hash.return_value = "swedish_hashed_password"

            result = await handler.reset_password(swedish_reset_password_request, correlation_id)

            assert isinstance(result, ResetPasswordResult)

            # Verify Swedish password passed correctly to hasher
            mock_password_hasher.hash.assert_called_once_with("Lösenord123!")

            # Verify password update with Swedish hash
            mock_user_repo.update_user_password.assert_called_once_with(
                sample_user_dict["id"], "swedish_hashed_password"
            )

        async def test_raises_error_for_invalid_token(
            self,
            handler: PasswordResetHandler,
            mock_user_repo: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_event_publisher: AsyncMock,
            mock_audit_logger: AsyncMock,
            valid_reset_password_request: ResetPasswordRequest,
            correlation_id: UUID,
        ) -> None:
            """Should raise HuleEduError for invalid token."""
            # Setup: token not found
            mock_user_repo.get_password_reset_token.return_value = None

            with pytest.raises(HuleEduError) as exc_info:
                await handler.reset_password(
                    valid_reset_password_request, correlation_id, ip_address="192.168.1.1"
                )

            error = exc_info.value
            assert "invalid" in str(error).lower()

            # Verify no password operations performed
            mock_password_hasher.hash.assert_not_called()
            mock_user_repo.update_user_password.assert_not_called()
            mock_user_repo.mark_reset_token_used.assert_not_called()
            mock_event_publisher.publish_password_reset_completed.assert_not_called()

            # Verify audit log for invalid token
            mock_audit_logger.log_action.assert_called_once_with(
                action="password_reset_invalid_token",
                user_id=None,
                details={"token": valid_reset_password_request.token[:8] + "..."},
                ip_address="192.168.1.1",
                user_agent=None,
                correlation_id=correlation_id,
            )

        async def test_raises_error_for_expired_token(
            self,
            handler: PasswordResetHandler,
            mock_user_repo: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_event_publisher: AsyncMock,
            mock_audit_logger: AsyncMock,
            valid_reset_password_request: ResetPasswordRequest,
            correlation_id: UUID,
        ) -> None:
            """Should raise HuleEduError for expired token."""
            # Setup: expired token
            expired_token_record = {
                "id": str(uuid4()),
                "user_id": str(uuid4()),
                "token": valid_reset_password_request.token,
                "expires_at": datetime.now(UTC) - timedelta(hours=1),  # Expired
                "used_at": None,
            }

            mock_user_repo.get_password_reset_token.return_value = expired_token_record

            with pytest.raises(HuleEduError) as exc_info:
                await handler.reset_password(
                    valid_reset_password_request, correlation_id, ip_address="192.168.1.1"
                )

            error = exc_info.value
            assert "expired" in str(error).lower()

            # Verify no password operations performed
            mock_password_hasher.hash.assert_not_called()
            mock_user_repo.update_user_password.assert_not_called()

            # Verify audit log for expired token
            user_id_str = expired_token_record["user_id"]
            expires_at_dt = expired_token_record["expires_at"]
            mock_audit_logger.log_action.assert_called_once_with(
                action="password_reset_token_expired",
                user_id=UUID(user_id_str) if isinstance(user_id_str, str) else None,
                details={
                    "token_id": expired_token_record["id"],
                    "expires_at": expires_at_dt.isoformat()
                    if hasattr(expires_at_dt, "isoformat")
                    else str(expires_at_dt),
                },
                ip_address="192.168.1.1",
                user_agent=None,
                correlation_id=correlation_id,
            )

        async def test_raises_error_for_already_used_token(
            self,
            handler: PasswordResetHandler,
            mock_user_repo: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_event_publisher: AsyncMock,
            mock_audit_logger: AsyncMock,
            valid_reset_password_request: ResetPasswordRequest,
            correlation_id: UUID,
        ) -> None:
            """Should raise HuleEduError for already used token."""
            # Setup: used token
            used_token_record = {
                "id": str(uuid4()),
                "user_id": str(uuid4()),
                "token": valid_reset_password_request.token,
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
                "used_at": datetime.now(UTC) - timedelta(minutes=30),  # Already used
            }

            mock_user_repo.get_password_reset_token.return_value = used_token_record

            with pytest.raises(HuleEduError) as exc_info:
                await handler.reset_password(
                    valid_reset_password_request, correlation_id, ip_address="192.168.1.1"
                )

            error = exc_info.value
            assert "invalid" in str(error).lower()

            # Verify no password operations performed
            mock_password_hasher.hash.assert_not_called()
            mock_user_repo.update_user_password.assert_not_called()

            # Verify audit log for already used token
            user_id_str = used_token_record["user_id"]
            used_at_dt = used_token_record["used_at"]
            mock_audit_logger.log_action.assert_called_once_with(
                action="password_reset_token_already_used",
                user_id=UUID(user_id_str) if isinstance(user_id_str, str) else None,
                details={
                    "token_id": used_token_record["id"],
                    "used_at": used_at_dt.isoformat()
                    if hasattr(used_at_dt, "isoformat")
                    else str(used_at_dt),
                },
                ip_address="192.168.1.1",
                user_agent=None,
                correlation_id=correlation_id,
            )

        async def test_raises_error_when_user_not_found(
            self,
            handler: PasswordResetHandler,
            mock_user_repo: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_event_publisher: AsyncMock,
            mock_audit_logger: AsyncMock,
            valid_reset_password_request: ResetPasswordRequest,
            correlation_id: UUID,
            sample_token_record: dict,
        ) -> None:
            """Should raise HuleEduError when user referenced by token is not found."""
            # Setup: valid token but user not found
            mock_user_repo.get_password_reset_token.return_value = sample_token_record
            mock_user_repo.get_user_by_id.return_value = None

            with pytest.raises(HuleEduError) as exc_info:
                await handler.reset_password(
                    valid_reset_password_request, correlation_id, ip_address="192.168.1.1"
                )

            error = exc_info.value
            assert "invalid" in str(error).lower()

            # Verify no password operations performed
            mock_password_hasher.hash.assert_not_called()
            mock_user_repo.update_user_password.assert_not_called()

            # Verify audit log for user not found
            mock_audit_logger.log_action.assert_called_once_with(
                action="password_reset_user_not_found",
                user_id=UUID(sample_token_record["user_id"]),
                details={"token_id": sample_token_record["id"]},
                ip_address="192.168.1.1",
                user_agent=None,
                correlation_id=correlation_id,
            )

        async def test_result_to_dict_serialization(
            self,
            handler: PasswordResetHandler,
            mock_user_repo: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_event_publisher: AsyncMock,
            mock_audit_logger: AsyncMock,
            valid_reset_password_request: ResetPasswordRequest,
            correlation_id: UUID,
            sample_user_dict: dict,
            sample_token_record: dict,
        ) -> None:
            """Should provide proper dictionary serialization for API responses."""
            mock_user_repo.get_password_reset_token.return_value = sample_token_record
            mock_user_repo.get_user_by_id.return_value = sample_user_dict
            mock_password_hasher.hash.return_value = "new_hash"

            result = await handler.reset_password(valid_reset_password_request, correlation_id)

            result_dict = result.to_dict()

            assert isinstance(result_dict, dict)
            assert result_dict["message"] == "Password reset successfully"
