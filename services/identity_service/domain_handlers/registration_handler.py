"""Registration domain handler for Identity Service.

Encapsulates user registration business logic including:
- User existence validation
- Password hashing
- User creation with transactional event publishing
- Comprehensive logging

This handler follows the established domain handler pattern from class_management_service.
"""

from __future__ import annotations

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
    UserRepo,
)

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
    - Event publishing for downstream services
    - Comprehensive audit logging
    """

    def __init__(
        self,
        user_repo: UserRepo,
        password_hasher: PasswordHasher,
        event_publisher: IdentityEventPublisherProtocol,
    ):
        self._user_repo = user_repo
        self._password_hasher = password_hasher
        self._event_publisher = event_publisher

    async def register_user(
        self,
        register_request: RegisterRequest,
        correlation_id: UUID,
    ) -> RegistrationResult:
        """Process user registration.

        Args:
            register_request: Registration data with email, org_id, and password
            correlation_id: Request correlation ID for observability

        Returns:
            RegistrationResult with created user data

        Raises:
            HuleEduError: If user already exists or validation fails
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

        # Publish user registered event
        await self._event_publisher.publish_user_registered(user, str(correlation_id))

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
