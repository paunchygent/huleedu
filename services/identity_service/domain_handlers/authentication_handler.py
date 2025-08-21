"""Authentication domain handler for Identity Service.

Encapsulates authentication business logic including:
- Login with rate limiting, account lockout, audit logging
- Logout with token revocation and event publishing
- Token refresh with session validation

This handler follows the established domain handler pattern from class_management_service.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from huleedu_service_libs.error_handling.factories import raise_rate_limit_error
from huleedu_service_libs.error_handling.identity_factories import (
    raise_account_locked_error,
    raise_invalid_credentials_error,
    raise_invalid_token_error,
    raise_missing_token_error,
    raise_user_not_found_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.identity_service.api.schemas import (
    LoginRequest,
    RefreshTokenRequest,
    RefreshTokenResponse,
    TokenPair,
)
from services.identity_service.implementations.rate_limiter_impl import create_rate_limit_key
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

logger = create_service_logger("identity_service.domain_handlers.authentication")


class LoginResult:
    """Result model for login operations."""

    def __init__(self, token_pair: TokenPair):
        self.token_pair = token_pair

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return self.token_pair.model_dump(mode="json")


class LogoutResult:
    """Result model for logout operations."""

    def __init__(self, message: str = "Logout successful"):
        self.message = message

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {"message": self.message}


class RefreshResult:
    """Result model for token refresh operations."""

    def __init__(self, response: RefreshTokenResponse):
        self.response = response

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return self.response.model_dump(mode="json")


class AuthenticationHandler:
    """Encapsulates authentication business logic for Identity Service.

    Handles login, logout, and token refresh operations with security features:
    - Rate limiting by IP and email
    - Account lockout after failed attempts
    - Comprehensive audit logging
    - Session management with device tracking
    - Event publishing for observability

    All methods accept client info (IP, user_agent) for security tracking.
    """

    def __init__(
        self,
        user_repo: UserRepo,
        token_issuer: TokenIssuer,
        password_hasher: PasswordHasher,
        session_repo: SessionRepo,
        user_session_repo: UserSessionRepositoryProtocol,
        event_publisher: IdentityEventPublisherProtocol,
        rate_limiter: RateLimiterProtocol,
        audit_logger: AuditLoggerProtocol,
    ):
        self._user_repo = user_repo
        self._token_issuer = token_issuer
        self._password_hasher = password_hasher
        self._session_repo = session_repo
        self._user_session_repo = user_session_repo
        self._event_publisher = event_publisher
        self._rate_limiter = rate_limiter
        self._audit_logger = audit_logger

    async def login(
        self,
        login_request: LoginRequest,
        correlation_id: UUID,
        ip_address: str | None,
        user_agent: str | None,
        device_name: str | None = None,
        device_type: str | None = None,
    ) -> LoginResult:
        """Process user login with full security features.

        Args:
            login_request: Login credentials
            correlation_id: Request correlation ID for observability
            ip_address: Client IP address for rate limiting and audit
            user_agent: Client user agent for audit logging
            device_name: Parsed device name (e.g., "Chrome")
            device_type: Parsed device type (e.g., "desktop", "mobile")

        Returns:
            LoginResult with access and refresh tokens

        Raises:
            HuleEduError: If rate limiting, authentication, or account lockout
        """
        # Rate limiting by IP and email
        ip_rate_key = create_rate_limit_key("login", ip_address or "unknown")
        email_rate_key = create_rate_limit_key("login", login_request.email)

        # Check IP rate limit (5 attempts per minute)
        ip_allowed, ip_remaining = await self._rate_limiter.check_rate_limit(
            ip_rate_key, limit=5, window_seconds=60
        )

        if not ip_allowed:
            await self._audit_logger.log_login_attempt(
                email=login_request.email,
                success=False,
                user_id=None,
                ip_address=ip_address,
                user_agent=user_agent,
                correlation_id=correlation_id,
                failure_reason="rate_limit_exceeded_ip",
            )

            logger.warning(
                "Login rate limit exceeded for IP",
                extra={
                    "ip_address": ip_address,
                    "email": login_request.email,
                    "correlation_id": str(correlation_id),
                },
            )

            raise_rate_limit_error(
                service="identity_service",
                operation="login",
                limit=5,
                window_seconds=60,
                message="Too many login attempts. Please try again later.",
                correlation_id=correlation_id,
                rate_type="ip_address",
            )

        # Check email rate limit (5 attempts per minute)
        email_allowed, email_remaining = await self._rate_limiter.check_rate_limit(
            email_rate_key, limit=5, window_seconds=60
        )

        if not email_allowed:
            await self._audit_logger.log_login_attempt(
                email=login_request.email,
                success=False,
                user_id=None,
                ip_address=ip_address,
                user_agent=user_agent,
                correlation_id=correlation_id,
                failure_reason="rate_limit_exceeded_email",
            )

            logger.warning(
                "Login rate limit exceeded for email",
                extra={
                    "email": login_request.email,
                    "ip_address": ip_address,
                    "correlation_id": str(correlation_id),
                },
            )

            raise_rate_limit_error(
                service="identity_service",
                operation="login",
                limit=5,
                window_seconds=60,
                message="Too many login attempts. Please try again later.",
                correlation_id=correlation_id,
                rate_type="ip_address",
            )

        # Increment rate limit counters
        await self._rate_limiter.increment(ip_rate_key, window_seconds=60)
        await self._rate_limiter.increment(email_rate_key, window_seconds=60)

        # Get user by email
        user = await self._user_repo.get_user_by_email(login_request.email)
        if not user:
            # Audit log failed attempt
            await self._audit_logger.log_login_attempt(
                email=login_request.email,
                success=False,
                user_id=None,
                ip_address=ip_address,
                user_agent=user_agent,
                correlation_id=correlation_id,
                failure_reason="user_not_found",
            )

            # Publish login failed event
            await self._event_publisher.publish_login_failed(
                login_request.email, "user_not_found", str(correlation_id)
            )

            logger.warning(
                "Login attempt for non-existent user",
                extra={
                    "email": login_request.email,
                    "correlation_id": str(correlation_id),
                },
            )

            raise_invalid_credentials_error(
                service="identity_service",
                operation="login",
                message="Invalid email or password",
                correlation_id=correlation_id,
                email=login_request.email,
            )

        # Check if account is locked
        if user.get("locked_until"):
            locked_until = user["locked_until"]
            if isinstance(locked_until, datetime):
                if locked_until > datetime.now(UTC):
                    await self._audit_logger.log_login_attempt(
                        email=login_request.email,
                        success=False,
                        user_id=user["id"],
                        ip_address=ip_address,
                        user_agent=user_agent,
                        correlation_id=correlation_id,
                        failure_reason="account_locked",
                    )

                    logger.warning(
                        "Login attempt for locked account",
                        extra={
                            "user_id": user["id"],
                            "email": login_request.email,
                            "locked_until": locked_until.isoformat(),
                            "correlation_id": str(correlation_id),
                        },
                    )

                    remaining_minutes = int((locked_until - datetime.now(UTC)).total_seconds() / 60)
                    raise_account_locked_error(
                        service="identity_service",
                        operation="login",
                        email=user["email"],
                        correlation_id=correlation_id,
                        locked_until=locked_until.isoformat(),
                        remaining_minutes=remaining_minutes,
                    )

        # Verify password
        if not self._password_hasher.verify(user.get("password_hash", ""), login_request.password):
            # Update failed login attempts
            failed_attempts = user.get("failed_login_attempts", 0) + 1

            # Lock account after 5 failed attempts
            update_data = {
                "failed_login_attempts": failed_attempts,
                "last_failed_login_at": datetime.now(UTC),
            }

            if failed_attempts >= 5:
                # Lock for 15 minutes
                update_data["locked_until"] = datetime.now(UTC) + timedelta(minutes=15)

                logger.warning(
                    "Account locked due to multiple failed login attempts",
                    extra={
                        "user_id": user["id"],
                        "email": login_request.email,
                        "failed_attempts": failed_attempts,
                        "correlation_id": str(correlation_id),
                    },
                )

            # Update user record with failed attempt info
            await self._user_repo.update_security_fields(user["id"], update_data)

            # Audit log failed attempt
            await self._audit_logger.log_login_attempt(
                email=login_request.email,
                success=False,
                user_id=user["id"],
                ip_address=ip_address,
                user_agent=user_agent,
                correlation_id=correlation_id,
                failure_reason="invalid_password",
            )

            # Publish login failed event
            await self._event_publisher.publish_login_failed(
                login_request.email, "invalid_password", str(correlation_id)
            )

            logger.warning(
                "Login attempt with invalid password",
                extra={
                    "user_id": user["id"],
                    "email": login_request.email,
                    "failed_attempts": failed_attempts,
                    "correlation_id": str(correlation_id),
                },
            )

            raise_invalid_credentials_error(
                service="identity_service",
                operation="login",
                message="Invalid email or password",
                correlation_id=correlation_id,
                email=login_request.email,
            )

        # Successful login - reset failed attempts and update last login
        await self._user_repo.update_security_fields(
            user["id"],
            {"failed_login_attempts": 0, "last_login_at": datetime.now(UTC), "locked_until": None},
        )

        # Generate tokens
        access = self._token_issuer.issue_access_token(
            user_id=user["id"], org_id=user.get("org_id"), roles=user.get("roles", [])
        )
        refresh, jti = self._token_issuer.issue_refresh_token(user_id=user["id"])

        # Store refresh session (backward compatibility)
        await self._session_repo.store_refresh(
            user_id=user["id"], jti=jti, exp_ts=int(time.time()) + 86400
        )

        # Store detailed session with device info
        await self._user_session_repo.create_session(
            user_id=user["id"],
            jti=jti,
            expires_at=datetime.now(UTC) + timedelta(days=1),
            device_name=device_name,
            device_type=device_type,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Audit log successful login
        await self._audit_logger.log_login_attempt(
            email=login_request.email,
            success=True,
            user_id=user["id"],
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )

        # Publish login succeeded event
        await self._event_publisher.publish_login_succeeded(user, str(correlation_id))

        logger.info(
            "User logged in successfully",
            extra={
                "user_id": user["id"],
                "email": login_request.email,
                "org_id": user.get("org_id"),
                "correlation_id": str(correlation_id),
            },
        )

        token_pair = TokenPair(access_token=access, refresh_token=refresh, expires_in=3600)
        return LoginResult(token_pair)

    async def logout(
        self,
        token: str,
        correlation_id: UUID,
    ) -> LogoutResult:
        """Process user logout with token revocation.

        Args:
            token: Access or refresh token to revoke
            correlation_id: Request correlation ID for observability

        Returns:
            LogoutResult with success message

        Raises:
            HuleEduError: If token is missing (not if invalid - security)
        """
        if not token:
            raise_missing_token_error(
                service="identity_service",
                operation="logout",
                message="No token provided for logout",
                correlation_id=correlation_id,
            )

        # Verify and extract token claims
        try:
            claims = self._token_issuer.verify(token)
            jti = claims.get("jti")
            user_id = claims.get("sub")

            if not user_id:
                raise ValueError("Invalid token format")

        except Exception as e:
            logger.warning(
                f"Invalid token during logout: {e}",
                extra={"correlation_id": str(correlation_id)},
            )
            # Still return success for security reasons
            return LogoutResult("Logout successful")

        # Revoke the refresh token if JTI is present (refresh tokens have JTI)
        if jti:
            await self._session_repo.revoke_refresh(jti)
            logger.info(
                "Refresh token revoked during logout",
                extra={
                    "jti": jti,
                    "user_id": user_id,
                    "correlation_id": str(correlation_id),
                },
            )

        # Publish logout event
        await self._event_publisher.publish_user_logged_out(
            user_id=user_id, correlation_id=str(correlation_id)
        )

        logger.info(
            "User logged out successfully",
            extra={
                "user_id": user_id,
                "correlation_id": str(correlation_id),
            },
        )

        return LogoutResult("Logout successful")

    async def refresh_token(
        self,
        refresh_request: RefreshTokenRequest,
        correlation_id: UUID,
    ) -> RefreshResult:
        """Exchange refresh token for new access token.

        Args:
            refresh_request: Refresh token request
            correlation_id: Request correlation ID for observability

        Returns:
            RefreshResult with new access token

        Raises:
            HuleEduError: If token is invalid, revoked, or user not found
        """
        # Verify the refresh token
        try:
            claims = self._token_issuer.verify(refresh_request.refresh_token)
            jti = claims.get("jti")
            user_id = claims.get("sub")

            if not jti or not user_id:
                raise_invalid_token_error(
                    service="identity_service",
                    operation="refresh_token",
                    message="Invalid refresh token format",
                    correlation_id=correlation_id,
                )
        except Exception as e:
            logger.warning(
                f"Invalid refresh token: {e}",
                extra={"correlation_id": str(correlation_id)},
            )
            raise_invalid_token_error(
                service="identity_service",
                operation="refresh_token",
                message="Invalid or expired refresh token",
                correlation_id=correlation_id,
            )

        # Check if the refresh token is still valid in the session store
        if not await self._session_repo.is_refresh_valid(jti):
            logger.warning(
                "Refresh token not found or revoked",
                extra={
                    "jti": jti,
                    "correlation_id": str(correlation_id),
                },
            )
            raise_invalid_token_error(
                service="identity_service",
                operation="refresh_token",
                message="Refresh token has been revoked",
                correlation_id=correlation_id,
            )

        # Get user details for new access token
        user = await self._user_repo.get_user_by_id(user_id)
        if not user:
            logger.error(
                "User not found for valid refresh token",
                extra={
                    "user_id": user_id,
                    "correlation_id": str(correlation_id),
                },
            )
            raise_user_not_found_error(
                service="identity_service",
                operation="refresh_token",
                identifier=user_id,
                correlation_id=correlation_id,
            )

        # Issue new access token with same claims as original
        access = self._token_issuer.issue_access_token(
            user_id=user["id"], org_id=user.get("org_id"), roles=user.get("roles", [])
        )

        logger.info(
            "Token refreshed successfully",
            extra={
                "user_id": user_id,
                "correlation_id": str(correlation_id),
            },
        )

        response = RefreshTokenResponse(
            access_token=access,
            expires_in=3600,  # 1 hour
        )
        return RefreshResult(response)
