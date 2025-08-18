"""
Unit tests for UserProfileHandler domain logic behavior.

Tests focus on business logic and behavior rather than implementation details.
Uses protocol-based mocking following established patterns.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from common_core.metadata_models import PersonNameV1
from huleedu_service_libs.error_handling import HuleEduError

from services.identity_service.domain_handlers.profile_handler import (
    ProfileRequest,
    ProfileResponse,
    UserProfileHandler,
)
from services.identity_service.models_db import UserProfile
from services.identity_service.protocols import UserProfileRepositoryProtocol


class TestUserProfileHandler:
    """Tests for UserProfileHandler business logic behavior."""

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create mock repository following protocol."""
        return AsyncMock(spec=UserProfileRepositoryProtocol)

    @pytest.fixture
    def handler(self, mock_repository: AsyncMock) -> UserProfileHandler:
        """Create handler with mocked repository."""
        return UserProfileHandler(repository=mock_repository)

    @pytest.fixture
    def sample_user_id(self) -> str:
        """Sample user ID for testing."""
        return str(uuid4())

    @pytest.fixture
    def correlation_id(self) -> UUID:
        """Sample correlation ID for testing."""
        return uuid4()

    @pytest.fixture
    def sample_profile(self, sample_user_id: str) -> UserProfile:
        """Create sample UserProfile for testing."""
        profile = UserProfile()
        profile.user_id = UUID(sample_user_id)
        profile.first_name = "Åsa"
        profile.last_name = "Öberg"
        profile.display_name = "Teacher Åsa"
        profile.locale = "sv-SE"
        return profile

    class TestGetProfile:
        """Tests for get_profile method behavior."""

        async def test_returns_profile_response_when_profile_exists(
            self,
            handler: UserProfileHandler,
            mock_repository: AsyncMock,
            sample_user_id: str,
            correlation_id: UUID,
            sample_profile: UserProfile,
        ) -> None:
            """Should return ProfileResponse with PersonNameV1 when profile exists."""
            mock_repository.get_profile.return_value = sample_profile

            result = await handler.get_profile(sample_user_id, correlation_id)

            assert isinstance(result, ProfileResponse)
            assert isinstance(result.person_name, PersonNameV1)
            assert result.person_name.first_name == "Åsa"
            assert result.person_name.last_name == "Öberg"
            assert result.person_name.legal_full_name == "Åsa Öberg"
            assert result.display_name == "Teacher Åsa"
            assert result.locale == "sv-SE"

            mock_repository.get_profile.assert_called_once_with(
                UUID(sample_user_id), correlation_id
            )

        async def test_raises_not_found_when_profile_missing(
            self,
            handler: UserProfileHandler,
            mock_repository: AsyncMock,
            sample_user_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should raise HuleEduError with 404 when profile not found."""
            mock_repository.get_profile.return_value = None

            with pytest.raises(HuleEduError) as exc_info:
                await handler.get_profile(sample_user_id, correlation_id)

            error = exc_info.value
            assert "UserProfile" in str(error)
            assert sample_user_id in str(error)

        @pytest.mark.parametrize(
            "invalid_user_id",
            [
                "not-a-uuid",
                "123-456-789",
                "",
                "completely-invalid",
            ],
        )
        async def test_raises_validation_error_for_invalid_user_id(
            self,
            handler: UserProfileHandler,
            mock_repository: AsyncMock,
            invalid_user_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should raise validation error for invalid UUID format."""
            with pytest.raises(HuleEduError) as exc_info:
                await handler.get_profile(invalid_user_id, correlation_id)

            error = exc_info.value
            assert "Invalid user_id format" in str(error)

            # Repository should not be called for invalid UUID
            mock_repository.get_profile.assert_not_called()

        async def test_handles_empty_names_gracefully(
            self,
            handler: UserProfileHandler,
            mock_repository: AsyncMock,
            sample_user_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should handle empty names by providing empty strings."""
            profile = UserProfile()
            profile.user_id = UUID(sample_user_id)
            profile.first_name = None
            profile.last_name = None
            profile.display_name = None
            profile.locale = None
            mock_repository.get_profile.return_value = profile

            result = await handler.get_profile(sample_user_id, correlation_id)

            assert result.person_name.first_name == ""
            assert result.person_name.last_name == ""
            assert result.person_name.legal_full_name == ""
            assert result.display_name is None
            assert result.locale is None

    class TestUpdateProfile:
        """Tests for update_profile method behavior."""

        @pytest.fixture
        def valid_request(self) -> ProfileRequest:
            """Create valid profile request."""
            return ProfileRequest(
                first_name="Karl",
                last_name="Ängström",
                display_name="Dr. Karl",
                locale="sv-SE",
            )

        async def test_creates_new_profile_successfully(
            self,
            handler: UserProfileHandler,
            mock_repository: AsyncMock,
            sample_user_id: str,
            correlation_id: UUID,
            valid_request: ProfileRequest,
        ) -> None:
            """Should create new profile and return ProfileResponse."""
            updated_profile = UserProfile()
            updated_profile.user_id = UUID(sample_user_id)
            updated_profile.first_name = "Karl"
            updated_profile.last_name = "Ängström"
            updated_profile.display_name = "Dr. Karl"
            updated_profile.locale = "sv-SE"
            mock_repository.upsert_profile.return_value = updated_profile

            result = await handler.update_profile(sample_user_id, valid_request, correlation_id)

            assert isinstance(result, ProfileResponse)
            assert result.person_name.first_name == "Karl"
            assert result.person_name.last_name == "Ängström"
            assert result.person_name.legal_full_name == "Karl Ängström"
            assert result.display_name == "Dr. Karl"
            assert result.locale == "sv-SE"

            mock_repository.upsert_profile.assert_called_once_with(
                UUID(sample_user_id),
                {
                    "first_name": "Karl",
                    "last_name": "Ängström",
                    "display_name": "Dr. Karl",
                    "locale": "sv-SE",
                },
                correlation_id,
            )

        @pytest.mark.parametrize(
            "first_name, last_name, should_raise",
            [
                ("", "Doe", True),  # Empty first name
                ("John", "", True),  # Empty last name
                ("   ", "Doe", True),  # Whitespace-only first name
                ("John", "   ", True),  # Whitespace-only last name
                ("John", "Doe", False),  # Valid names
                ("  John  ", "  Doe  ", False),  # Names with whitespace (should be stripped)
            ],
        )
        async def test_validates_required_fields(
            self,
            handler: UserProfileHandler,
            mock_repository: AsyncMock,
            sample_user_id: str,
            correlation_id: UUID,
            first_name: str,
            last_name: str,
            should_raise: bool,
        ) -> None:
            """Should validate required first_name and last_name fields."""
            if should_raise:
                with pytest.raises(ValueError):
                    ProfileRequest(
                        first_name=first_name,
                        last_name=last_name,
                    )
            else:
                request = ProfileRequest(
                    first_name=first_name,
                    last_name=last_name,
                )

                # For valid requests, verify whitespace is stripped
                if not should_raise:
                    profile_data = request.to_profile_data()
                    assert profile_data["first_name"] == first_name.strip()
                    assert profile_data["last_name"] == last_name.strip()

        async def test_handles_none_optional_fields(
            self,
            handler: UserProfileHandler,
            mock_repository: AsyncMock,
            sample_user_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should handle None values for optional fields."""
            request = ProfileRequest(
                first_name="Jane",
                last_name="Smith",
                display_name=None,
                locale=None,
            )

            updated_profile = UserProfile()
            updated_profile.user_id = UUID(sample_user_id)
            updated_profile.first_name = "Jane"
            updated_profile.last_name = "Smith"
            updated_profile.display_name = None
            updated_profile.locale = None
            mock_repository.upsert_profile.return_value = updated_profile

            result = await handler.update_profile(sample_user_id, request, correlation_id)

            assert result.display_name is None
            assert result.locale is None

            # Verify repository call includes None values
            call_args = mock_repository.upsert_profile.call_args[0]
            profile_data = call_args[1]
            assert profile_data["display_name"] is None
            assert profile_data["locale"] is None

        @pytest.mark.parametrize(
            "invalid_user_id",
            [
                "not-a-uuid",
                "123-456-789",
                "",
            ],
        )
        async def test_validates_user_id_format_on_update(
            self,
            handler: UserProfileHandler,
            mock_repository: AsyncMock,
            invalid_user_id: str,
            correlation_id: UUID,
            valid_request: ProfileRequest,
        ) -> None:
            """Should validate user_id format before updating."""
            with pytest.raises(HuleEduError) as exc_info:
                await handler.update_profile(invalid_user_id, valid_request, correlation_id)

            error = exc_info.value
            assert "Invalid user_id format" in str(error)

            # Repository should not be called for invalid UUID
            mock_repository.upsert_profile.assert_not_called()

        async def test_strips_whitespace_from_fields(
            self,
            handler: UserProfileHandler,
            mock_repository: AsyncMock,
            sample_user_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should strip whitespace from all string fields."""
            request = ProfileRequest(
                first_name="  John  ",
                last_name="  Doe  ",
                display_name="  Professor John  ",
                locale="  en-US  ",
            )

            updated_profile = UserProfile()
            updated_profile.user_id = UUID(sample_user_id)
            updated_profile.first_name = "John"
            updated_profile.last_name = "Doe"
            updated_profile.display_name = "Professor John"
            updated_profile.locale = "en-US"
            mock_repository.upsert_profile.return_value = updated_profile

            await handler.update_profile(sample_user_id, request, correlation_id)

            # Verify repository receives stripped values
            call_args = mock_repository.upsert_profile.call_args[0]
            profile_data = call_args[1]
            assert profile_data["first_name"] == "John"
            assert profile_data["last_name"] == "Doe"
            assert profile_data["display_name"] == "Professor John"
            assert profile_data["locale"] == "en-US"
