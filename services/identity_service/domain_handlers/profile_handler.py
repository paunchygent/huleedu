from __future__ import annotations

from typing import Any
from uuid import UUID

from common_core.metadata_models import PersonNameV1
from huleedu_service_libs.error_handling import raise_resource_not_found, raise_validation_error

from services.identity_service.models_db import UserProfile
from services.identity_service.protocols import UserProfileRepositoryProtocol


class ProfileResponse:
    """Response model for profile operations."""

    def __init__(
        self, person_name: PersonNameV1, display_name: str | None = None, locale: str | None = None
    ):
        self.person_name = person_name
        self.display_name = display_name
        self.locale = locale

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "person_name": {
                "first_name": self.person_name.first_name,
                "last_name": self.person_name.last_name,
                "legal_full_name": self.person_name.legal_full_name,
            },
            "display_name": self.display_name,
            "locale": self.locale,
        }


class ProfileRequest:
    """Request model for profile updates."""

    def __init__(
        self,
        first_name: str,
        last_name: str,
        display_name: str | None = None,
        locale: str | None = None,
    ):
        self.first_name = first_name
        self.last_name = last_name
        self.display_name = display_name
        self.locale = locale

        # Validate required fields
        if not first_name or not first_name.strip():
            raise ValueError("first_name is required")
        if not last_name or not last_name.strip():
            raise ValueError("last_name is required")

    def to_profile_data(self) -> dict[str, Any]:
        """Convert to dictionary for repository operations."""
        return {
            "first_name": self.first_name.strip(),
            "last_name": self.last_name.strip(),
            "display_name": self.display_name.strip() if self.display_name else None,
            "locale": self.locale.strip() if self.locale else None,
        }


class UserProfileHandler:
    """Encapsulates profile business logic for future extraction to dedicated service."""

    def __init__(self, repository: UserProfileRepositoryProtocol):
        self._repository = repository

    async def get_profile(self, user_id: str, correlation_id: UUID) -> ProfileResponse:
        """Get user profile with PersonNameV1 structure.

        Args:
            user_id: The user's ID as string
            correlation_id: Request correlation ID for observability

        Returns:
            ProfileResponse with PersonNameV1 and additional fields

        Raises:
            HuleEduError: If profile not found or database error
        """
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            raise_validation_error(
                service="identity_service",
                operation="get_user_profile",
                field="user_id",
                message="Invalid user_id format",
                correlation_id=correlation_id,
            )

        profile = await self._repository.get_profile(user_uuid, correlation_id)

        if not profile:
            raise_resource_not_found(
                service="identity_service",
                operation="get_user_profile",
                resource_type="UserProfile",
                resource_id=user_id,
                correlation_id=correlation_id,
            )

        return self._profile_to_response(profile)

    async def update_profile(
        self, user_id: str, request: ProfileRequest, correlation_id: UUID
    ) -> ProfileResponse:
        """Create or update user profile.

        Args:
            user_id: The user's ID as string
            request: Profile update request with validated data
            correlation_id: Request correlation ID for observability

        Returns:
            ProfileResponse with updated data

        Raises:
            HuleEduError: If validation fails or database error
        """
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            raise_validation_error(
                service="identity_service",
                operation="update_user_profile",
                field="user_id",
                message="Invalid user_id format",
                correlation_id=correlation_id,
            )

        try:
            profile_data = request.to_profile_data()
        except ValueError as e:
            raise_validation_error(
                service="identity_service",
                operation="update_user_profile",
                field="profile_data",
                message=str(e),
                correlation_id=correlation_id,
            )

        updated_profile = await self._repository.upsert_profile(
            user_uuid, profile_data, correlation_id
        )

        return self._profile_to_response(updated_profile)

    def _profile_to_response(self, profile: UserProfile) -> ProfileResponse:
        """Convert UserProfile DB model to ProfileResponse.

        Args:
            profile: UserProfile database model

        Returns:
            ProfileResponse with PersonNameV1 structure
        """
        # Create PersonNameV1 with computed legal_full_name
        person_name = PersonNameV1(
            first_name=profile.first_name or "",
            last_name=profile.last_name or "",
            # PersonNameV1 model_validator will compute legal_full_name automatically
        )

        return ProfileResponse(
            person_name=person_name,
            display_name=profile.display_name,
            locale=profile.locale,
        )
