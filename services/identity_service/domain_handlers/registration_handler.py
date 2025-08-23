"""Registration domain handler for Identity Service.

Encapsulates user registration business logic including:
- User existence validation
- Password hashing
- User creation with transactional event publishing
- Comprehensive logging

This handler follows the established domain handler pattern from class_management_service.
"""

from __future__ import annotations

# Import VerificationHandler - late import to avoid circular dependency
from typing import TYPE_CHECKING
from uuid import UUID

from huleedu_service_libs.error_handling.identity_factories import (
    raise_user_already_exists_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.identity_service.api.schemas import (
    RegisterRequest,
    RegisterResponse,
)
from services.identity_service.protocols import (
    IdentityEventPublisherProtocol,
    PasswordHasher,
    UserProfileRepositoryProtocol,
    UserRepo,
)

if TYPE_CHECKING:
    from services.identity_service.domain_handlers.verification_handler import VerificationHandler

logger = create_service_logger("identity_service.domain_handlers.registration")


class RegistrationResult:
    """Result model for registration operations."""

    def __init__(self, response: RegisterResponse):
        self.response = response

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return self.response.model_dump(mode="json")


class RegistrationHandler:
    """Encapsulates user registration business logic for Identity Service.

    Handles user registration with:
    - Email uniqueness validation
    - Secure password hashing
    - Transactional user creation
    - User profile creation with person_name data
    - Event publishing for downstream services
    - Comprehensive audit logging
    """

    def __init__(
        self,
        user_repo: UserRepo,
        password_hasher: PasswordHasher,
        event_publisher: IdentityEventPublisherProtocol,
        verification_handler: "VerificationHandler",
        profile_repository: UserProfileRepositoryProtocol,
    ):
        self._user_repo = user_repo
        self._password_hasher = password_hasher
        self._event_publisher = event_publisher
        self._verification_handler = verification_handler
        self._profile_repository = profile_repository

    async def register_user(
        self,
        register_request: RegisterRequest,
        correlation_id: UUID,
    ) -> RegistrationResult:
        """Process user registration with profile creation.

        Args:
            register_request: Registration data with email, password, person_name, and organization
            correlation_id: Request correlation ID for observability

        Returns:
            RegistrationResult with created user data

        Raises:
            HuleEduError: If user already exists, validation fails, or profile creation fails
        """
        # Check if user already exists
        existing_user = await self._user_repo.get_user_by_email(register_request.email)
        if existing_user:
            raise_user_already_exists_error(
                service="identity_service",
                operation="register",
                email=register_request.email,
                correlation_id=correlation_id,
            )

        # Create user (this should be transactional with event publishing)
        user = await self._user_repo.create_user(
            register_request.email,
            register_request.org_id,
            self._password_hasher.hash(register_request.password),
        )

        # Create user profile with person_name data
        profile_data = {
            "first_name": register_request.person_name.first_name,
            "last_name": register_request.person_name.last_name,
            "display_name": None,  # Can be set later via profile update
            "locale": None,  # Can be set later via profile update
        }

        user_uuid = UUID(user["id"])
        await self._profile_repository.upsert_profile(user_uuid, profile_data, correlation_id)

        logger.info(
            "User profile created during registration",
            extra={
                "user_id": user["id"],
                "first_name": register_request.person_name.first_name,
                "last_name": register_request.person_name.last_name,
                "correlation_id": str(correlation_id),
            },
        )

        # Publish user registered event
        await self._event_publisher.publish_user_registered(user, str(correlation_id))

        # Automatically send email verification (best practice: verify before login)
        try:
            await self._verification_handler.request_email_verification_by_email(
                email=register_request.email,
                correlation_id=correlation_id,
            )
            logger.info(
                "Email verification sent automatically after registration",
                extra={
                    "user_id": user["id"],
                    "email": register_request.email,
                    "correlation_id": str(correlation_id),
                },
            )
        except Exception as e:
            # Log warning but don't fail registration if verification email fails
            logger.warning(
                "Failed to send automatic verification email after registration",
                extra={
                    "user_id": user["id"],
                    "email": register_request.email,
                    "correlation_id": str(correlation_id),
                    "error": str(e),
                },
                exc_info=True,
            )

        logger.info(
            "User registered successfully",
            extra={
                "user_id": user["id"],
                "email": register_request.email,
                "org_id": register_request.org_id,
                "correlation_id": str(correlation_id),
            },
        )

        # Transform user dict to match RegisterResponse schema
        response_data = {
            "user_id": user["id"],  # Map 'id' to 'user_id'
            "email": user["email"],
            "org_id": user["org_id"],
            "email_verification_required": user.get("email_verification_required", True),
        }

        response = RegisterResponse(**response_data)
        return RegistrationResult(response)
