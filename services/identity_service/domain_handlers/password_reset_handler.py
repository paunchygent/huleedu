"""Password reset domain handler for Identity Service.

Encapsulates password reset business logic including:
- Secure password reset token generation and validation
- Token expiration and usage tracking (1-hour expiry for security)
- Password hashing and updating
- Security-focused user lookup (no email existence revelation)
- Event publishing for password reset workflows
- Comprehensive audit logging with security considerations

This handler follows the established domain handler pattern from class_management_service.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from huleedu_service_libs.error_handling.identity_factories import (
    raise_verification_token_expired_error,
    raise_verification_token_invalid_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.identity_service.api.schemas import (
    RequestPasswordResetRequest,
    RequestPasswordResetResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
)
from services.identity_service.protocols import (
    AuditLoggerProtocol,
    IdentityEventPublisherProtocol,
    PasswordHasher,
    UserRepo,
)

logger = create_service_logger("identity_service.domain_handlers.password_reset")


class RequestPasswordResetResult:
    """Result model for password reset request operations."""
    
    def __init__(self, response: RequestPasswordResetResponse):
        self.response = response
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return self.response.model_dump(mode="json")


class ResetPasswordResult:
    """Result model for password reset operations."""
    
    def __init__(self, response: ResetPasswordResponse):
        self.response = response
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return self.response.model_dump(mode="json")


class PasswordResetHandler:
    """Encapsulates password reset business logic for Identity Service.
    
    Handles password reset workflow with security-first approach:
    - Email lookup without revealing user existence (security best practice)
    - Token generation with 1-hour expiration for security
    - Token validation (existence, expiration, usage)
    - Secure password hashing with bcrypt/similar
    - Transactional token marking and password updates
    - Event publishing for downstream services
    - Comprehensive audit logging for security monitoring
    """
    
    def __init__(
        self,
        user_repo: UserRepo,
        password_hasher: PasswordHasher,
        event_publisher: IdentityEventPublisherProtocol,
        audit_logger: AuditLoggerProtocol,
    ):
        self._user_repo = user_repo
        self._password_hasher = password_hasher
        self._event_publisher = event_publisher
        self._audit_logger = audit_logger
    
    async def request_password_reset(
        self,
        reset_request: RequestPasswordResetRequest,
        correlation_id: UUID,
        ip_address: str | None = None,
    ) -> RequestPasswordResetResult:
        """Request password reset token for a user.
        
        Security note: Always returns success regardless of whether email exists.
        This prevents email enumeration attacks.
        
        Args:
            reset_request: Password reset request with email
            correlation_id: Request correlation ID for observability
            ip_address: Client IP address for audit logging
            
        Returns:
            RequestPasswordResetResult with generic success message
            
        Raises:
            HuleEduError: Only for unexpected errors, not for user validation
        """
        # Security: Look up user by email but don't reveal if it exists
        user = await self._user_repo.get_user_by_email(reset_request.email)

        # Always return success (security best practice)
        response = RequestPasswordResetResponse(
            message="If the email address exists, a password reset link will be sent",
            correlation_id=str(correlation_id),
        )

        # Only proceed if user exists
        if user:
            # Invalidate existing password reset tokens for this user
            await self._user_repo.invalidate_password_reset_tokens(user["id"])

            # Generate new password reset token
            token = str(uuid.uuid4())
            expires_at = datetime.now(UTC) + timedelta(hours=1)  # 1 hour expiry for security

            # Create password reset token
            token_record = await self._user_repo.create_password_reset_token(
                user["id"], token, expires_at
            )

            # Audit log password reset request
            await self._audit_logger.log_action(
                action="password_reset_requested",
                user_id=UUID(user["id"]) if user["id"] else None,
                details={
                    "email": user["email"],
                    "token_id": token_record["id"],
                    "expires_at": expires_at.isoformat(),
                },
                ip_address=ip_address,
                user_agent=None,
                correlation_id=correlation_id
            )

            # Publish password reset requested event
            await self._event_publisher.publish_password_reset_requested(
                user, token_record["id"], expires_at, str(correlation_id)
            )

            logger.info(
                "Password reset requested successfully",
                extra={
                    "user_id": user["id"],
                    "email": user["email"],
                    "token_id": token_record["id"],
                    "correlation_id": str(correlation_id),
                },
            )
        else:
            # Audit log attempt for non-existent email (security monitoring)
            await self._audit_logger.log_action(
                action="password_reset_requested_nonexistent",
                user_id=None,
                details={"email": reset_request.email},
                ip_address=ip_address,
                user_agent=None,
                correlation_id=correlation_id
            )
            
            logger.info(
                "Password reset requested for non-existent email (security: no revelation)",
                extra={
                    "email": reset_request.email,
                    "correlation_id": str(correlation_id),
                },
            )

        return RequestPasswordResetResult(response)
    
    async def reset_password(
        self,
        reset_request: ResetPasswordRequest,
        correlation_id: UUID,
        ip_address: str | None = None,
    ) -> ResetPasswordResult:
        """Reset password using valid reset token.
        
        Args:
            reset_request: Password reset with token and new password
            correlation_id: Request correlation ID for observability
            ip_address: Client IP address for audit logging
            
        Returns:
            ResetPasswordResult with success message
            
        Raises:
            HuleEduError: If token invalid, expired, used, or user not found
        """
        # Get password reset token
        token_record = await self._user_repo.get_password_reset_token(reset_request.token)

        if not token_record:
            await self._audit_logger.log_action(
                action="password_reset_invalid_token",
                user_id=None,
                details={"token": reset_request.token[:8] + "..."},
                ip_address=ip_address,
                user_agent=None,
                correlation_id=correlation_id
            )
            
            raise_verification_token_invalid_error(
                service="identity_service",
                operation="reset_password",
                correlation_id=correlation_id,
            )

        # Check if token is already used
        if token_record["used_at"] is not None:
            await self._audit_logger.log_action(
                action="password_reset_token_already_used",
                user_id=UUID(token_record["user_id"]) if token_record.get("user_id") else None,
                details={
                    "token_id": token_record["id"],
                    "used_at": token_record["used_at"].isoformat(),
                },
                ip_address=ip_address,
                user_agent=None,
                correlation_id=correlation_id
            )
            
            raise_verification_token_invalid_error(
                service="identity_service",
                operation="reset_password",
                correlation_id=correlation_id,
            )

        # Check if token is expired
        if datetime.now(UTC) > token_record["expires_at"]:
            await self._audit_logger.log_action(
                action="password_reset_token_expired",
                user_id=UUID(token_record["user_id"]) if token_record.get("user_id") else None,
                details={
                    "token_id": token_record["id"],
                    "expires_at": token_record["expires_at"].isoformat(),
                },
                ip_address=ip_address,
                user_agent=None,
                correlation_id=correlation_id
            )
            
            raise_verification_token_expired_error(
                service="identity_service",
                operation="reset_password",
                correlation_id=correlation_id,
            )

        # Get user for password update (from token's user_id)
        user = await self._user_repo.get_user_by_id(token_record["user_id"])

        if not user:
            await self._audit_logger.log_action(
                action="password_reset_user_not_found",
                user_id=UUID(token_record["user_id"]) if token_record.get("user_id") else None,
                details={"token_id": token_record["id"]},
                ip_address=ip_address,
                user_agent=None,
                correlation_id=correlation_id
            )
            
            raise_verification_token_invalid_error(
                service="identity_service",
                operation="reset_password",
                correlation_id=correlation_id,
            )

        # Hash the new password
        new_password_hash = self._password_hasher.hash(reset_request.new_password)

        # Update password and mark token as used (transactional)
        await self._user_repo.update_user_password(user["id"], new_password_hash)
        await self._user_repo.mark_reset_token_used(token_record["id"])

        # Audit log successful password reset
        await self._audit_logger.log_action(
            action="password_reset_completed",
            user_id=UUID(user["id"]) if user["id"] else None,
            details={"email": user["email"], "token_id": token_record["id"]},
            ip_address=ip_address,
            user_agent=None,
            correlation_id=correlation_id
        )

        # Publish password reset completed event
        await self._event_publisher.publish_password_reset_completed(user, str(correlation_id))

        logger.info(
            "Password reset completed successfully",
            extra={
                "user_id": user["id"],
                "email": user["email"],
                "token_id": token_record["id"],
                "correlation_id": str(correlation_id),
            },
        )

        response = ResetPasswordResponse(message="Password reset successfully")
        return ResetPasswordResult(response)
    
    async def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
        correlation_id: UUID,
        ip_address: str | None = None,
    ) -> ResetPasswordResult:
        """Change password for authenticated user (optional future endpoint).
        
        Args:
            user_id: Authenticated user ID from JWT/session
            current_password: Current password for verification
            new_password: New password to set
            correlation_id: Request correlation ID for observability
            ip_address: Client IP address for audit logging
            
        Returns:
            ResetPasswordResult with success message
            
        Raises:
            HuleEduError: If current password invalid or user not found
        """
        # Get user by ID
        user = await self._user_repo.get_user_by_id(user_id)
        if not user:
            raise_verification_token_invalid_error(
                service="identity_service",
                operation="change_password",
                correlation_id=correlation_id,
            )

        # Verify current password
        if not self._password_hasher.verify(user.get("password_hash", ""), current_password):
            await self._audit_logger.log_action(
                action="password_change_invalid_current",
                user_id=UUID(user["id"]) if user["id"] else None,
                details={"email": user["email"]},
                ip_address=ip_address,
                user_agent=None,
                correlation_id=correlation_id
            )
            
            raise_verification_token_invalid_error(
                service="identity_service",
                operation="change_password",
                correlation_id=correlation_id,
            )

        # Hash new password and update
        new_password_hash = self._password_hasher.hash(new_password)
        await self._user_repo.update_user_password(user["id"], new_password_hash)

        # Audit log successful password change
        await self._audit_logger.log_action(
            action="password_change_completed",
            user_id=UUID(user["id"]) if user["id"] else None,
            details={"email": user["email"]},
            ip_address=ip_address,
            user_agent=None,
            correlation_id=correlation_id
        )

        logger.info(
            "Password changed successfully",
            extra={
                "user_id": user["id"],
                "email": user["email"],
                "correlation_id": str(correlation_id),
            },
        )

        response = ResetPasswordResponse(message="Password changed successfully")
        return ResetPasswordResult(response)