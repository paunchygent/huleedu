from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Protocol
from uuid import UUID

from common_core.identity_enums import LoginFailureReason
from services.identity_service.models_db import UserProfile


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, hash: str, password: str) -> bool: ...


class TokenIssuer(Protocol):
    def issue_access_token(self, user_id: str, org_id: str | None, roles: list[str]) -> str: ...
    def issue_refresh_token(self, user_id: str) -> tuple[str, str]: ...  # token, jti
    def verify(self, token: str) -> dict: ...


class UserRepo(Protocol):
    async def create_user(self, email: str, org_id: str | None, password_hash: str) -> dict: ...
    async def get_user_by_email(self, email: str) -> Optional[dict]: ...
    async def get_user_by_id(self, user_id: str) -> Optional[dict]: ...
    async def set_email_verified(self, user_id: str) -> None: ...
    async def create_email_verification_token(
        self, user_id: str, token: str, expires_at: datetime
    ) -> dict: ...
    async def get_email_verification_token(self, token: str) -> Optional[dict]: ...
    async def mark_token_used(self, token_id: str) -> None: ...
    async def invalidate_user_tokens(self, user_id: str) -> None: ...
    async def create_password_reset_token(
        self, user_id: str, token: str, expires_at: datetime
    ) -> dict: ...
    async def get_password_reset_token(self, token: str) -> Optional[dict]: ...
    async def mark_reset_token_used(self, token_id: str) -> None: ...
    async def invalidate_password_reset_tokens(self, user_id: str) -> None: ...
    async def update_user_password(self, user_id: str, password_hash: str) -> None: ...
    async def update_security_fields(self, user_id: str, fields: dict[str, Any]) -> None: ...


class SessionRepo(Protocol):
    async def store_refresh(self, user_id: str, jti: str, exp_ts: int) -> None: ...
    async def revoke_refresh(self, jti: str) -> None: ...
    async def is_refresh_valid(self, jti: str) -> bool: ...


class IdentityEventPublisherProtocol(Protocol):
    async def publish_user_registered(self, user: dict, correlation_id: str) -> None: ...

    async def publish_login_succeeded(self, user: dict, correlation_id: str) -> None: ...

    async def publish_login_failed(
        self, email: str, failure_reason: LoginFailureReason, correlation_id: str
    ) -> None: ...

    async def publish_email_verification_requested(
        self, user: dict, token_id: str, expires_at: datetime, correlation_id: str
    ) -> None: ...

    async def publish_email_verified(self, user: dict, correlation_id: str) -> None: ...

    async def publish_password_reset_requested(
        self, user: dict, token_id: str, expires_at: datetime, correlation_id: str
    ) -> None: ...

    async def publish_password_reset_completed(self, user: dict, correlation_id: str) -> None: ...

    async def publish_user_logged_out(self, user_id: str, correlation_id: str) -> None: ...


class UserProfileRepositoryProtocol(Protocol):
    async def get_profile(self, user_id: UUID, correlation_id: UUID) -> UserProfile | None: ...
    async def upsert_profile(
        self, user_id: UUID, profile_data: dict, correlation_id: UUID
    ) -> UserProfile: ...


class RateLimiterProtocol(Protocol):
    """Protocol for rate limiting functionality."""

    async def check_rate_limit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """
        Check if a rate limit allows the operation.

        Args:
            key: The rate limit key (e.g., "login:ip:192.168.1.1")
            limit: Maximum number of attempts allowed
            window_seconds: Time window in seconds

        Returns:
            Tuple of (allowed, remaining_attempts)
        """
        ...

    async def increment(self, key: str, window_seconds: int) -> int:
        """
        Increment the counter for a rate limit key.

        Args:
            key: The rate limit key
            window_seconds: TTL for the key

        Returns:
            New count after increment
        """
        ...

    async def reset(self, key: str) -> bool:
        """Reset a rate limit key."""
        ...


class AuditLoggerProtocol(Protocol):
    """Protocol for audit logging functionality."""

    async def log_action(
        self,
        action: str,
        user_id: UUID | None,
        details: dict[str, Any] | None,
        ip_address: str | None,
        user_agent: str | None,
        correlation_id: UUID,
    ) -> None:
        """
        Log an audit event.

        Args:
            action: The action being performed (e.g., "login_attempt", "password_reset")
            user_id: User ID if authenticated
            details: Additional details about the action
            ip_address: Client IP address
            user_agent: Client user agent string
            correlation_id: Request correlation ID
        """
        ...

    async def log_login_attempt(
        self,
        email: str,
        success: bool,
        user_id: UUID | None,
        ip_address: str | None,
        user_agent: str | None,
        correlation_id: UUID,
        failure_reason: LoginFailureReason | None = None,
    ) -> None:
        """Log a login attempt."""
        ...

    async def log_password_change(
        self, user_id: UUID, ip_address: str | None, user_agent: str | None, correlation_id: UUID
    ) -> None:
        """Log a password change."""
        ...

    async def log_token_operation(
        self,
        operation: str,
        user_id: UUID,
        jti: str | None,
        ip_address: str | None,
        user_agent: str | None,
        correlation_id: UUID,
    ) -> None:
        """Log token operations (refresh, revoke, etc.)."""
        ...


class UserSessionRepositoryProtocol(Protocol):
    """Protocol for user session management with device tracking."""

    async def create_session(
        self,
        user_id: UUID,
        jti: str,
        expires_at: datetime,
        device_name: str | None,
        device_type: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        """Create a new user session."""
        ...

    async def get_user_sessions(self, user_id: UUID) -> list[dict[str, Any]]:
        """Get all active sessions for a user."""
        ...

    async def revoke_session(self, jti: str) -> bool:
        """Revoke a specific session."""
        ...

    async def revoke_all_user_sessions(self, user_id: UUID) -> int:
        """Revoke all sessions for a user."""
        ...

    async def update_last_activity(self, jti: str) -> bool:
        """Update the last activity timestamp for a session."""
        ...

    async def get_session(self, jti: str) -> dict[str, Any] | None:
        """Get session details by JTI."""
        ...

    async def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions from the database."""
        ...
