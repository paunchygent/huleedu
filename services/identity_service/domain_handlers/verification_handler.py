"""Email verification domain handler for Identity Service.

Encapsulates email verification business logic including:
- Email verification token generation and validation
- Token expiration and usage tracking
- User email verification status updates
- Event publishing for verification workflows

This handler follows the established domain handler pattern from class_management_service.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from huleedu_service_libs.error_handling.identity_factories import (
    raise_email_already_verified_error,
    raise_user_not_found_error,
    raise_verification_token_expired_error,
    raise_verification_token_invalid_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.identity_service.api.schemas import (
    RequestEmailVerificationRequest,
    RequestEmailVerificationResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from services.identity_service.protocols import (
    IdentityEventPublisherProtocol,
    UserRepo,
)

logger = create_service_logger("identity_service.domain_handlers.verification")


class RequestVerificationResult:
    """Result model for email verification request operations."""

    def __init__(self, response: RequestEmailVerificationResponse):
        self.response = response

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return self.response.model_dump(mode="json")


class VerifyEmailResult:
    """Result model for email verification operations."""

    def __init__(self, response: VerifyEmailResponse):
        self.response = response

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return self.response.model_dump(mode="json")


class VerificationHandler:
    """Encapsulates email verification business logic for Identity Service.

    Handles email verification workflow with:
    - Token generation with configurable expiration (24 hours)
    - Email already verified validation
    - Token validation (existence, expiration, usage)
    - Transactional token marking and email verification
    - Event publishing for downstream services
    - Comprehensive audit logging
    """

    def __init__(
        self,
        user_repo: UserRepo,
        event_publisher: IdentityEventPublisherProtocol,
    ):
        self._user_repo = user_repo
        self._event_publisher = event_publisher

    async def request_email_verification(
        self,
        request_data: RequestEmailVerificationRequest,
        user_id: str,  # From JWT or session context
        correlation_id: UUID,
    ) -> RequestVerificationResult:
        """Request email verification token for a user.

        Args:
            request_data: Verification request data
            user_id: User ID from authenticated context (JWT/session)
            correlation_id: Request correlation ID for observability

        Returns:
            RequestVerificationResult with success message

        Raises:
            HuleEduError: If email already verified or user not found
        """
        # Get user by ID from authenticated context
        user = await self._user_repo.get_user_by_id(user_id)
        if not user:
            # This should not happen in production with proper auth middleware
            logger.error(
                "User not found for authenticated request",
                extra={
                    "user_id": user_id,
                    "correlation_id": str(correlation_id),
                },
            )
            raise_verification_token_invalid_error(
                service="identity_service",
                operation="request_email_verification",
                correlation_id=correlation_id,
            )

        # Check if email is already verified
        if user["email_verified"]:
            raise_email_already_verified_error(
                service="identity_service",
                operation="request_email_verification",
                email=user["email"],
                correlation_id=correlation_id,
            )

        # Invalidate existing tokens for this user
        await self._user_repo.invalidate_user_tokens(user["id"])

        # Generate new verification token
        token = str(uuid.uuid4())
        expires_at = datetime.now(UTC) + timedelta(hours=24)

        # Create verification token
        token_record = await self._user_repo.create_email_verification_token(
            user["id"], token, expires_at
        )

        # Publish email verification requested event
        await self._event_publisher.publish_email_verification_requested(
            user, token, expires_at, str(correlation_id)
        )

        logger.info(
            "Email verification requested successfully",
            extra={
                "user_id": user["id"],
                "email": user["email"],
                "token_id": token_record["id"],
                "correlation_id": str(correlation_id),
            },
        )

        response = RequestEmailVerificationResponse(
            message="Email verification token generated successfully",
            correlation_id=str(correlation_id),
        )
        return RequestVerificationResult(response)

    async def request_email_verification_by_email(
        self,
        email: str,
        correlation_id: UUID,
    ) -> RequestVerificationResult:
        """Request email verification token for a user by email (public endpoint).

        This method is used for initial verification requests from unregistered users
        or users who need to resend their verification email.

        Args:
            email: Email address to send verification to
            correlation_id: Request correlation ID for observability

        Returns:
            RequestVerificationResult with success message

        Raises:
            HuleEduError: If email already verified or user not found
        """
        # Get user by email
        user = await self._user_repo.get_user_by_email(email)
        if not user:
            logger.warning(
                "Verification requested for non-existent user",
                extra={
                    "email": email,
                    "correlation_id": str(correlation_id),
                },
            )
            raise_user_not_found_error(
                service="identity_service",
                operation="request_email_verification_by_email",
                identifier=email,
                correlation_id=correlation_id,
            )

        # Check if email is already verified
        if user["email_verified"]:
            raise_email_already_verified_error(
                service="identity_service",
                operation="request_email_verification_by_email",
                email=user["email"],
                correlation_id=correlation_id,
            )

        # Invalidate existing tokens for this user
        await self._user_repo.invalidate_user_tokens(user["id"])

        # Generate new verification token
        token = str(uuid.uuid4())
        expires_at = datetime.now(UTC) + timedelta(hours=24)

        # Create verification token
        token_record = await self._user_repo.create_email_verification_token(
            user["id"], token, expires_at
        )

        # Publish email verification requested event
        await self._event_publisher.publish_email_verification_requested(
            user, token, expires_at, str(correlation_id)
        )

        logger.info(
            "Email verification requested successfully (public)",
            extra={
                "user_id": user["id"],
                "email": user["email"],
                "token_id": token_record["id"],
                "correlation_id": str(correlation_id),
            },
        )

        response = RequestEmailVerificationResponse(
            message="Email verification token generated successfully",
            correlation_id=str(correlation_id),
        )
        return RequestVerificationResult(response)

    async def verify_email(
        self,
        verify_request: VerifyEmailRequest,
        correlation_id: UUID,
    ) -> VerifyEmailResult:
        """Verify email using verification token.

        Args:
            verify_request: Verification token request
            correlation_id: Request correlation ID for observability

        Returns:
            VerifyEmailResult with success message

        Raises:
            HuleEduError: If token invalid, expired, used, or email already verified
        """
        # Get verification token
        token_record = await self._user_repo.get_email_verification_token(verify_request.token)

        if not token_record:
            raise_verification_token_invalid_error(
                service="identity_service",
                operation="verify_email",
                correlation_id=correlation_id,
            )

        # Check if token is already used
        if token_record["used_at"] is not None:
            raise_verification_token_invalid_error(
                service="identity_service",
                operation="verify_email",
                correlation_id=correlation_id,
            )

        # Check if token is expired
        if datetime.now(UTC) > token_record["expires_at"]:
            raise_verification_token_expired_error(
                service="identity_service",
                operation="verify_email",
                correlation_id=correlation_id,
            )

        # Get user for verification (from token's user_id)
        user = await self._user_repo.get_user_by_id(token_record["user_id"])

        if not user:
            raise_verification_token_invalid_error(
                service="identity_service",
                operation="verify_email",
                correlation_id=correlation_id,
            )

        # Check if email is already verified
        if user["email_verified"]:
            raise_email_already_verified_error(
                service="identity_service",
                operation="verify_email",
                email=user["email"],
                correlation_id=correlation_id,
            )

        # Mark token as used and set email as verified (transactional)
        await self._user_repo.mark_token_used(token_record["id"])
        await self._user_repo.set_email_verified(user["id"])

        # Publish email verified event
        await self._event_publisher.publish_email_verified(user, str(correlation_id))

        logger.info(
            "Email verified successfully",
            extra={
                "user_id": user["id"],
                "email": user["email"],
                "token_id": token_record["id"],
                "correlation_id": str(correlation_id),
            },
        )

        response = VerifyEmailResponse(message="Email verified successfully")
        return VerifyEmailResult(response)
