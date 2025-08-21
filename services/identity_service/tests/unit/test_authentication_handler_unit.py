"""
Unit tests for AuthenticationHandler domain logic behavior.

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
    LoginRequest,
    RefreshTokenRequest,
    RefreshTokenResponse,
    TokenPair,
)
from services.identity_service.domain_handlers.authentication_handler import (
    AuthenticationHandler,
    LoginResult,
    LogoutResult,
    RefreshResult,
)
from services.identity_service.protocols import (
    AuditLoggerProtocol,
    IdentityEventPublisherProtocol,
    PasswordHasher,
    RateLimiterProtocol,
    SessionRepo,
    TokenIssuer,
    UserRepo,
    UserSessionRepositoryProtocol,
)


class TestAuthenticationHandler:
    """Tests for AuthenticationHandler business logic behavior."""

    @pytest.fixture
    def mock_user_repo(self) -> AsyncMock:
        """Create mock user repository following protocol."""
        return AsyncMock(spec=UserRepo)

    @pytest.fixture
    def mock_token_issuer(self) -> AsyncMock:
        """Create mock token issuer following protocol."""
        return AsyncMock(spec=TokenIssuer)

    @pytest.fixture
    def mock_password_hasher(self) -> AsyncMock:
        """Create mock password hasher following protocol."""
        return AsyncMock(spec=PasswordHasher)

    @pytest.fixture
    def mock_session_repo(self) -> AsyncMock:
        """Create mock session repository following protocol."""
        return AsyncMock(spec=SessionRepo)

    @pytest.fixture
    def mock_user_session_repo(self) -> AsyncMock:
        """Create mock user session repository following protocol."""
        return AsyncMock(spec=UserSessionRepositoryProtocol)

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher following protocol."""
        return AsyncMock(spec=IdentityEventPublisherProtocol)

    @pytest.fixture
    def mock_rate_limiter(self) -> AsyncMock:
        """Create mock rate limiter following protocol."""
        return AsyncMock(spec=RateLimiterProtocol)

    @pytest.fixture
    def mock_audit_logger(self) -> AsyncMock:
        """Create mock audit logger following protocol."""
        return AsyncMock(spec=AuditLoggerProtocol)

    @pytest.fixture
    def handler(
        self,
        mock_user_repo: AsyncMock,
        mock_token_issuer: AsyncMock,
        mock_password_hasher: AsyncMock,
        mock_session_repo: AsyncMock,
        mock_user_session_repo: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_rate_limiter: AsyncMock,
        mock_audit_logger: AsyncMock,
    ) -> AuthenticationHandler:
        """Create handler with all mocked dependencies."""
        return AuthenticationHandler(
            user_repo=mock_user_repo,
            token_issuer=mock_token_issuer,
            password_hasher=mock_password_hasher,
            session_repo=mock_session_repo,
            user_session_repo=mock_user_session_repo,
            event_publisher=mock_event_publisher,
            rate_limiter=mock_rate_limiter,
            audit_logger=mock_audit_logger,
        )

    @pytest.fixture
    def correlation_id(self) -> UUID:
        """Sample correlation ID for testing."""
        return uuid4()

    @pytest.fixture
    def sample_user_id(self) -> str:
        """Sample user ID for testing."""
        return str(uuid4())

    @pytest.fixture
    def sample_user(self, sample_user_id: str) -> dict:
        """Create sample user data for testing with Swedish characters."""
        return {
            "id": sample_user_id,
            "email": "åsa.öberg@exempel.se",
            "password_hash": "hashed_password_123",
            "org_id": "org_123",
            "roles": ["teacher", "admin"],
            "failed_login_attempts": 0,
            "last_login_at": None,
            "locked_until": None,
        }

    @pytest.fixture
    def login_request(self) -> LoginRequest:
        """Create login request with Swedish characters."""
        return LoginRequest(
            email="åsa.öberg@exempel.se",
            password="mySecurePassword123",
        )

    class TestLogin:
        """Tests for login method behavior."""

        async def test_successful_login_flow(
            self,
            handler: AuthenticationHandler,
            mock_user_repo: AsyncMock,
            mock_token_issuer: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_session_repo: AsyncMock,
            mock_user_session_repo: AsyncMock,
            mock_event_publisher: AsyncMock,
            mock_rate_limiter: AsyncMock,
            mock_audit_logger: AsyncMock,
            login_request: LoginRequest,
            sample_user: dict,
            correlation_id: UUID,
        ) -> None:
            """Should successfully login user with valid credentials."""
            # Arrange
            mock_rate_limiter.check_rate_limit.return_value = (True, 4)
            mock_user_repo.get_user_by_email.return_value = sample_user
            mock_password_hasher.verify.return_value = True
            mock_token_issuer.issue_access_token.return_value = "access_token_123"
            mock_token_issuer.issue_refresh_token.return_value = ("refresh_token_123", "jti_123")

            # Act
            result = await handler.login(
                login_request=login_request,
                correlation_id=correlation_id,
                ip_address="192.168.1.100",
                user_agent="Mozilla/5.0 Chrome/91.0",
                device_name="Chrome",
                device_type="desktop",
            )

            # Assert
            assert isinstance(result, LoginResult)
            assert isinstance(result.token_pair, TokenPair)
            assert result.token_pair.access_token == "access_token_123"
            assert result.token_pair.refresh_token == "refresh_token_123"
            assert result.token_pair.expires_in == 3600

            # Verify rate limiting checks
            assert mock_rate_limiter.check_rate_limit.call_count == 2
            assert mock_rate_limiter.increment.call_count == 2

            # Verify user lookup and password verification
            mock_user_repo.get_user_by_email.assert_called_once_with(login_request.email)
            mock_password_hasher.verify.assert_called_once_with(
                sample_user["password_hash"], login_request.password
            )

            # Verify security fields reset
            mock_user_repo.update_security_fields.assert_called_once()
            call_args = mock_user_repo.update_security_fields.call_args[0]
            update_data = call_args[1]
            assert update_data["failed_login_attempts"] == 0
            assert "last_login_at" in update_data
            assert update_data["locked_until"] is None

            # Verify token generation
            mock_token_issuer.issue_access_token.assert_called_once_with(
                user_id=sample_user["id"],
                org_id=sample_user["org_id"],
                roles=sample_user["roles"],
            )
            mock_token_issuer.issue_refresh_token.assert_called_once_with(user_id=sample_user["id"])

            # Verify session storage
            mock_session_repo.store_refresh.assert_called_once()
            mock_user_session_repo.create_session.assert_called_once()

            # Verify audit logging
            mock_audit_logger.log_login_attempt.assert_called_once_with(
                email=login_request.email,
                success=True,
                user_id=sample_user["id"],
                ip_address="192.168.1.100",
                user_agent="Mozilla/5.0 Chrome/91.0",
                correlation_id=correlation_id,
            )

            # Verify event publishing
            mock_event_publisher.publish_login_succeeded.assert_called_once_with(
                sample_user, str(correlation_id)
            )

        async def test_login_fails_for_non_existent_user(
            self,
            handler: AuthenticationHandler,
            mock_user_repo: AsyncMock,
            mock_rate_limiter: AsyncMock,
            mock_audit_logger: AsyncMock,
            mock_event_publisher: AsyncMock,
            login_request: LoginRequest,
            correlation_id: UUID,
        ) -> None:
            """Should raise invalid credentials error when user not found."""
            # Arrange
            mock_rate_limiter.check_rate_limit.return_value = (True, 4)
            mock_user_repo.get_user_by_email.return_value = None

            # Act & Assert
            with pytest.raises(HuleEduError) as exc_info:
                await handler.login(
                    login_request=login_request,
                    correlation_id=correlation_id,
                    ip_address="192.168.1.100",
                    user_agent="Mozilla/5.0 Chrome/91.0",
                )

            error = exc_info.value
            assert "Invalid email or password" in str(error)

            # Verify audit logging
            mock_audit_logger.log_login_attempt.assert_called_once_with(
                email=login_request.email,
                success=False,
                user_id=None,
                ip_address="192.168.1.100",
                user_agent="Mozilla/5.0 Chrome/91.0",
                correlation_id=correlation_id,
                failure_reason="user_not_found",
            )

            # Verify event publishing
            mock_event_publisher.publish_login_failed.assert_called_once_with(
                login_request.email, "user_not_found", str(correlation_id)
            )

        async def test_login_fails_for_invalid_password(
            self,
            handler: AuthenticationHandler,
            mock_user_repo: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_rate_limiter: AsyncMock,
            mock_audit_logger: AsyncMock,
            mock_event_publisher: AsyncMock,
            login_request: LoginRequest,
            sample_user: dict,
            correlation_id: UUID,
        ) -> None:
            """Should raise invalid credentials error and update failed attempts."""
            # Arrange
            mock_rate_limiter.check_rate_limit.return_value = (True, 4)
            mock_user_repo.get_user_by_email.return_value = sample_user
            mock_password_hasher.verify.return_value = False

            # Act & Assert
            with pytest.raises(HuleEduError) as exc_info:
                await handler.login(
                    login_request=login_request,
                    correlation_id=correlation_id,
                    ip_address="192.168.1.100",
                    user_agent="Mozilla/5.0 Chrome/91.0",
                )

            error = exc_info.value
            assert "Invalid email or password" in str(error)

            # Verify failed attempts are incremented
            mock_user_repo.update_security_fields.assert_called_once()
            call_args = mock_user_repo.update_security_fields.call_args[0]
            update_data = call_args[1]
            assert update_data["failed_login_attempts"] == 1
            assert "last_failed_login_at" in update_data

            # Verify audit logging
            mock_audit_logger.log_login_attempt.assert_called_once_with(
                email=login_request.email,
                success=False,
                user_id=sample_user["id"],
                ip_address="192.168.1.100",
                user_agent="Mozilla/5.0 Chrome/91.0",
                correlation_id=correlation_id,
                failure_reason="invalid_password",
            )

            # Verify event publishing
            mock_event_publisher.publish_login_failed.assert_called_once_with(
                login_request.email, "invalid_password", str(correlation_id)
            )

        async def test_login_triggers_account_lockout_after_five_failures(
            self,
            handler: AuthenticationHandler,
            mock_user_repo: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_rate_limiter: AsyncMock,
            login_request: LoginRequest,
            sample_user: dict,
            correlation_id: UUID,
        ) -> None:
            """Should lock account after 5 failed login attempts."""
            # Arrange
            sample_user["failed_login_attempts"] = 4  # One more will trigger lockout
            mock_rate_limiter.check_rate_limit.return_value = (True, 4)
            mock_user_repo.get_user_by_email.return_value = sample_user
            mock_password_hasher.verify.return_value = False

            # Act & Assert
            with pytest.raises(HuleEduError):
                await handler.login(
                    login_request=login_request,
                    correlation_id=correlation_id,
                    ip_address="192.168.1.100",
                    user_agent="Mozilla/5.0 Chrome/91.0",
                )

            # Verify account is locked
            call_args = mock_user_repo.update_security_fields.call_args[0]
            update_data = call_args[1]
            assert update_data["failed_login_attempts"] == 5
            assert "locked_until" in update_data
            assert isinstance(update_data["locked_until"], datetime)

        async def test_login_fails_for_locked_account(
            self,
            handler: AuthenticationHandler,
            mock_user_repo: AsyncMock,
            mock_rate_limiter: AsyncMock,
            mock_audit_logger: AsyncMock,
            login_request: LoginRequest,
            sample_user: dict,
            correlation_id: UUID,
        ) -> None:
            """Should raise account locked error for locked accounts."""
            # Arrange
            locked_until = datetime.now(UTC) + timedelta(minutes=10)
            sample_user["locked_until"] = locked_until
            mock_rate_limiter.check_rate_limit.return_value = (True, 4)
            mock_user_repo.get_user_by_email.return_value = sample_user

            # Act & Assert
            with pytest.raises(HuleEduError) as exc_info:
                await handler.login(
                    login_request=login_request,
                    correlation_id=correlation_id,
                    ip_address="192.168.1.100",
                    user_agent="Mozilla/5.0 Chrome/91.0",
                )

            error = exc_info.value
            assert "locked" in str(error).lower()

            # Verify audit logging
            mock_audit_logger.log_login_attempt.assert_called_once_with(
                email=login_request.email,
                success=False,
                user_id=sample_user["id"],
                ip_address="192.168.1.100",
                user_agent="Mozilla/5.0 Chrome/91.0",
                correlation_id=correlation_id,
                failure_reason="account_locked",
            )

        async def test_login_blocked_by_ip_rate_limit(
            self,
            handler: AuthenticationHandler,
            mock_rate_limiter: AsyncMock,
            mock_audit_logger: AsyncMock,
            login_request: LoginRequest,
            correlation_id: UUID,
        ) -> None:
            """Should raise rate limit error when IP limit exceeded."""
            # Arrange
            mock_rate_limiter.check_rate_limit.return_value = (False, 0)

            # Act & Assert
            with pytest.raises(HuleEduError) as exc_info:
                await handler.login(
                    login_request=login_request,
                    correlation_id=correlation_id,
                    ip_address="192.168.1.100",
                    user_agent="Mozilla/5.0 Chrome/91.0",
                )

            error = exc_info.value
            assert "Too many login attempts" in str(error)

            # Verify audit logging
            mock_audit_logger.log_login_attempt.assert_called_once_with(
                email=login_request.email,
                success=False,
                user_id=None,
                ip_address="192.168.1.100",
                user_agent="Mozilla/5.0 Chrome/91.0",
                correlation_id=correlation_id,
                failure_reason="rate_limit_exceeded_ip",
            )

        async def test_login_blocked_by_email_rate_limit(
            self,
            handler: AuthenticationHandler,
            mock_rate_limiter: AsyncMock,
            mock_audit_logger: AsyncMock,
            login_request: LoginRequest,
            correlation_id: UUID,
        ) -> None:
            """Should raise rate limit error when email limit exceeded."""
            # Arrange - IP allowed, email blocked
            mock_rate_limiter.check_rate_limit.side_effect = [(True, 4), (False, 0)]

            # Act & Assert
            with pytest.raises(HuleEduError) as exc_info:
                await handler.login(
                    login_request=login_request,
                    correlation_id=correlation_id,
                    ip_address="192.168.1.100",
                    user_agent="Mozilla/5.0 Chrome/91.0",
                )

            error = exc_info.value
            assert "Too many login attempts" in str(error)

            # Verify audit logging
            mock_audit_logger.log_login_attempt.assert_called_once_with(
                email=login_request.email,
                success=False,
                user_id=None,
                ip_address="192.168.1.100",
                user_agent="Mozilla/5.0 Chrome/91.0",
                correlation_id=correlation_id,
                failure_reason="rate_limit_exceeded_email",
            )

    class TestLogout:
        """Tests for logout method behavior."""

        async def test_successful_logout_with_valid_token(
            self,
            handler: AuthenticationHandler,
            mock_token_issuer: AsyncMock,
            mock_session_repo: AsyncMock,
            mock_event_publisher: AsyncMock,
            sample_user_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should successfully logout user and revoke refresh token."""
            # Arrange
            test_token = "valid_refresh_token_123"
            test_jti = "jti_123"
            mock_token_issuer.verify.return_value = {
                "sub": sample_user_id,
                "jti": test_jti,
            }

            # Act
            result = await handler.logout(
                token=test_token,
                correlation_id=correlation_id,
            )

            # Assert
            assert isinstance(result, LogoutResult)
            assert result.message == "Logout successful"

            # Verify token verification
            mock_token_issuer.verify.assert_called_once_with(test_token)

            # Verify session revocation
            mock_session_repo.revoke_refresh.assert_called_once_with(test_jti)

            # Verify event publishing
            mock_event_publisher.publish_user_logged_out.assert_called_once_with(
                user_id=sample_user_id, correlation_id=str(correlation_id)
            )

        async def test_logout_with_missing_token_raises_error(
            self,
            handler: AuthenticationHandler,
            correlation_id: UUID,
        ) -> None:
            """Should raise missing token error when no token provided."""
            # Act & Assert
            with pytest.raises(HuleEduError) as exc_info:
                await handler.logout(
                    token="",
                    correlation_id=correlation_id,
                )

            error = exc_info.value
            assert "No token provided" in str(error)

        async def test_logout_with_invalid_token_still_succeeds_for_security(
            self,
            handler: AuthenticationHandler,
            mock_token_issuer: AsyncMock,
            mock_session_repo: AsyncMock,
            mock_event_publisher: AsyncMock,
            correlation_id: UUID,
        ) -> None:
            """Should return success even with invalid token for security reasons."""
            # Arrange
            test_token = "invalid_token_123"
            mock_token_issuer.verify.side_effect = Exception("Invalid token")

            # Act
            result = await handler.logout(
                token=test_token,
                correlation_id=correlation_id,
            )

            # Assert
            assert isinstance(result, LogoutResult)
            assert result.message == "Logout successful"

            # Verify no session operations performed
            mock_session_repo.revoke_refresh.assert_not_called()
            mock_event_publisher.publish_user_logged_out.assert_not_called()

        async def test_logout_with_access_token_without_jti(
            self,
            handler: AuthenticationHandler,
            mock_token_issuer: AsyncMock,
            mock_session_repo: AsyncMock,
            mock_event_publisher: AsyncMock,
            sample_user_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should handle access tokens without JTI gracefully."""
            # Arrange
            test_token = "access_token_without_jti"
            mock_token_issuer.verify.return_value = {
                "sub": sample_user_id,
                # No JTI for access token
            }

            # Act
            result = await handler.logout(
                token=test_token,
                correlation_id=correlation_id,
            )

            # Assert
            assert isinstance(result, LogoutResult)
            assert result.message == "Logout successful"

            # Verify no session revocation (access tokens don't have JTI)
            mock_session_repo.revoke_refresh.assert_not_called()

            # Verify event still published
            mock_event_publisher.publish_user_logged_out.assert_called_once_with(
                user_id=sample_user_id, correlation_id=str(correlation_id)
            )

    class TestRefreshToken:
        """Tests for refresh_token method behavior."""

        async def test_successful_token_refresh(
            self,
            handler: AuthenticationHandler,
            mock_token_issuer: AsyncMock,
            mock_session_repo: AsyncMock,
            mock_user_repo: AsyncMock,
            sample_user: dict,
            correlation_id: UUID,
        ) -> None:
            """Should successfully refresh access token with valid refresh token."""
            # Arrange
            refresh_request = RefreshTokenRequest(refresh_token="valid_refresh_token_123")
            test_jti = "jti_123"
            new_access_token = "new_access_token_456"

            mock_token_issuer.verify.return_value = {
                "sub": sample_user["id"],
                "jti": test_jti,
            }
            mock_session_repo.is_refresh_valid.return_value = True
            mock_user_repo.get_user_by_id.return_value = sample_user
            mock_token_issuer.issue_access_token.return_value = new_access_token

            # Act
            result = await handler.refresh_token(
                refresh_request=refresh_request,
                correlation_id=correlation_id,
            )

            # Assert
            assert isinstance(result, RefreshResult)
            assert isinstance(result.response, RefreshTokenResponse)
            assert result.response.access_token == new_access_token
            assert result.response.expires_in == 3600

            # Verify token verification
            mock_token_issuer.verify.assert_called_once_with(refresh_request.refresh_token)

            # Verify session validation
            mock_session_repo.is_refresh_valid.assert_called_once_with(test_jti)

            # Verify user lookup
            mock_user_repo.get_user_by_id.assert_called_once_with(sample_user["id"])

            # Verify new access token generation
            mock_token_issuer.issue_access_token.assert_called_once_with(
                user_id=sample_user["id"],
                org_id=sample_user["org_id"],
                roles=sample_user["roles"],
            )

        async def test_refresh_token_fails_with_invalid_token_format(
            self,
            handler: AuthenticationHandler,
            mock_token_issuer: AsyncMock,
            correlation_id: UUID,
        ) -> None:
            """Should raise invalid token error for malformed tokens."""
            # Arrange
            refresh_request = RefreshTokenRequest(refresh_token="invalid_token_123")
            mock_token_issuer.verify.side_effect = Exception("Invalid token")

            # Act & Assert
            with pytest.raises(HuleEduError) as exc_info:
                await handler.refresh_token(
                    refresh_request=refresh_request,
                    correlation_id=correlation_id,
                )

            error = exc_info.value
            assert "Invalid or expired refresh token" in str(error)

        async def test_refresh_token_fails_with_missing_jti(
            self,
            handler: AuthenticationHandler,
            mock_token_issuer: AsyncMock,
            correlation_id: UUID,
        ) -> None:
            """Should raise invalid token error when JTI is missing."""
            # Arrange
            refresh_request = RefreshTokenRequest(refresh_token="token_without_jti")
            mock_token_issuer.verify.return_value = {
                "sub": "user_123",
                # No JTI
            }

            # Act & Assert
            with pytest.raises(HuleEduError) as exc_info:
                await handler.refresh_token(
                    refresh_request=refresh_request,
                    correlation_id=correlation_id,
                )

            error = exc_info.value
            # Note: Due to implementation logic, the specific error message is caught
            # by the generic exception handler and returns this message instead
            assert "Invalid or expired refresh token" in str(error)

        async def test_refresh_token_fails_with_revoked_token(
            self,
            handler: AuthenticationHandler,
            mock_token_issuer: AsyncMock,
            mock_session_repo: AsyncMock,
            sample_user_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should raise invalid token error when refresh token is revoked."""
            # Arrange
            refresh_request = RefreshTokenRequest(refresh_token="revoked_token_123")
            test_jti = "revoked_jti_123"

            mock_token_issuer.verify.return_value = {
                "sub": sample_user_id,
                "jti": test_jti,
            }
            mock_session_repo.is_refresh_valid.return_value = False

            # Act & Assert
            with pytest.raises(HuleEduError) as exc_info:
                await handler.refresh_token(
                    refresh_request=refresh_request,
                    correlation_id=correlation_id,
                )

            error = exc_info.value
            assert "Refresh token has been revoked" in str(error)

        async def test_refresh_token_fails_when_user_not_found(
            self,
            handler: AuthenticationHandler,
            mock_token_issuer: AsyncMock,
            mock_session_repo: AsyncMock,
            mock_user_repo: AsyncMock,
            sample_user_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should raise user not found error when user is deleted."""
            # Arrange
            refresh_request = RefreshTokenRequest(refresh_token="orphaned_token_123")
            test_jti = "orphaned_jti_123"

            mock_token_issuer.verify.return_value = {
                "sub": sample_user_id,
                "jti": test_jti,
            }
            mock_session_repo.is_refresh_valid.return_value = True
            mock_user_repo.get_user_by_id.return_value = None

            # Act & Assert
            with pytest.raises(HuleEduError) as exc_info:
                await handler.refresh_token(
                    refresh_request=refresh_request,
                    correlation_id=correlation_id,
                )

            error = exc_info.value
            assert "User not found" in str(error) or sample_user_id in str(error)

        @pytest.mark.parametrize(
            "swedish_email",
            [
                "märta.ängström@skola.se",
                "björn.öberg@universitet.se",
                "åsa.åkerström@gymnasium.se",
            ],
        )
        async def test_login_handles_swedish_email_addresses(
            self,
            handler: AuthenticationHandler,
            mock_rate_limiter: AsyncMock,
            mock_user_repo: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_token_issuer: AsyncMock,
            mock_session_repo: AsyncMock,
            mock_user_session_repo: AsyncMock,
            mock_audit_logger: AsyncMock,
            mock_event_publisher: AsyncMock,
            sample_user_id: str,
            correlation_id: UUID,
            swedish_email: str,
        ) -> None:
            """Should handle Swedish email addresses correctly during login."""
            # Arrange
            login_request = LoginRequest(email=swedish_email, password="testPassword123")
            swedish_user = {
                "id": sample_user_id,
                "email": swedish_email,
                "password_hash": "hashed_password",
                "org_id": "org_123",
                "roles": ["teacher"],
                "failed_login_attempts": 0,
                "last_login_at": None,
                "locked_until": None,
            }

            mock_rate_limiter.check_rate_limit.return_value = (True, 4)
            mock_user_repo.get_user_by_email.return_value = swedish_user
            mock_password_hasher.verify.return_value = True
            mock_token_issuer.issue_access_token.return_value = "access_token"
            mock_token_issuer.issue_refresh_token.return_value = ("refresh_token", "jti")

            # Act
            result = await handler.login(
                login_request=login_request,
                correlation_id=correlation_id,
                ip_address="192.168.1.100",
                user_agent="Mozilla/5.0",
            )

            # Assert
            assert isinstance(result, LoginResult)
            mock_user_repo.get_user_by_email.assert_called_once_with(swedish_email)
            mock_audit_logger.log_login_attempt.assert_called_once()
            mock_event_publisher.publish_login_succeeded.assert_called_once()
