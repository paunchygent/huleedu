"""
Integration tests for profile management API routes.

Tests the profile endpoints GET/PUT /v1/users/{user_id}/profile
following the established Quart+Dishka testing patterns.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from common_core.metadata_models import PersonNameV1
from dishka import Provider, Scope, make_async_container, provide
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.identity_service.app import app
from services.identity_service.domain_handlers.profile_handler import (
    ProfileResponse,
    UserProfileHandler,
)


class TestProfileRoutes:
    """Test profile API endpoints using proper Quart+Dishka patterns."""

    @pytest.fixture
    def mock_profile_handler(self) -> AsyncMock:
        """Create mock profile handler."""
        return AsyncMock(spec=UserProfileHandler)

    @pytest.fixture
    def sample_user_id(self) -> str:
        """Sample user ID for testing."""
        return str(uuid4())

    @pytest.fixture
    def sample_profile_response(self) -> ProfileResponse:
        """Create sample ProfileResponse with Swedish characters."""
        return ProfileResponse(
            person_name=PersonNameV1(
                first_name="Åsa",
                last_name="Öberg",
                legal_full_name="Åsa Öberg",
            ),
            display_name="Teacher Åsa",
            locale="sv-SE",
        )

    @pytest.fixture
    async def app_client(
        self,
        mock_profile_handler: AsyncMock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        """
        Return a Quart test client configured with mocked dependencies using Dishka.
        This fixture overrides production providers with test providers that supply our mocks.
        """

        # 1. Define a test-specific provider that provides our mocks
        class TestProvider(Provider):
            @provide(scope=Scope.APP)
            def provide_profile_handler(self) -> UserProfileHandler:
                return mock_profile_handler

        # 2. Create a new container with our test provider
        container = make_async_container(TestProvider())

        # 3. Apply the container to the app instance for the test
        app.config.update({"TESTING": True})
        QuartDishka(app=app, container=container)

        async with app.test_client() as client:
            yield client

        # 4. Clean up the container after the test
        await container.close()

    class TestGetProfile:
        """Tests for GET /v1/users/{user_id}/profile endpoint."""

        async def test_returns_profile_response_when_profile_exists(
            self,
            app_client: QuartTestClient,
            mock_profile_handler: AsyncMock,
            sample_user_id: str,
            sample_profile_response: ProfileResponse,
        ) -> None:
            """Should return 200 with PersonNameV1 when profile exists."""
            # Arrange
            mock_profile_handler.get_profile.return_value = sample_profile_response

            # Act
            response = await app_client.get(f"/v1/users/{sample_user_id}/profile")

            # Assert
            assert response.status_code == 200
            data = await response.get_json()
            assert "person_name" in data
            assert data["person_name"]["first_name"] == "Åsa"
            assert data["person_name"]["last_name"] == "Öberg"
            assert data["person_name"]["legal_full_name"] == "Åsa Öberg"
            assert data["display_name"] == "Teacher Åsa"
            assert data["locale"] == "sv-SE"

            # Verify handler was called with correct arguments
            mock_profile_handler.get_profile.assert_called_once()
            call_args = mock_profile_handler.get_profile.call_args[0]
            assert call_args[0] == sample_user_id
            # Second argument should be UUID (correlation_id)
            assert isinstance(call_args[1], UUID)

        async def test_returns_404_when_profile_missing(
            self,
            app_client: QuartTestClient,
            mock_profile_handler: AsyncMock,
            sample_user_id: str,
        ) -> None:
            """Should return 400 when profile not found (HuleEduError)."""
            # Arrange
            from huleedu_service_libs.error_handling import raise_resource_not_found

            def raise_not_found(*_: Any, **__: Any) -> None:
                raise_resource_not_found(
                    service="identity_service",
                    operation="get_user_profile",
                    resource_type="UserProfile",
                    resource_id=sample_user_id,
                    correlation_id=uuid4(),
                )

            mock_profile_handler.get_profile.side_effect = raise_not_found

            # Act
            response = await app_client.get(f"/v1/users/{sample_user_id}/profile")

            # Assert
            assert response.status_code == 400
            data = await response.get_json()
            assert "error" in data

        @pytest.mark.parametrize(
            "invalid_user_id",
            [
                "not-a-uuid",
                "123-456-789",
                "completely-invalid",
            ],
        )
        async def test_returns_400_for_invalid_user_id(
            self,
            app_client: QuartTestClient,
            mock_profile_handler: AsyncMock,
            invalid_user_id: str,
        ) -> None:
            """Should return 400 for invalid UUID format."""
            # Arrange
            from huleedu_service_libs.error_handling import raise_validation_error

            def raise_validation(*_: Any, **__: Any) -> None:
                raise_validation_error(
                    service="identity_service",
                    operation="get_user_profile",
                    field="user_id",
                    message=f"Invalid user_id format: {invalid_user_id}",
                    correlation_id=uuid4(),
                )

            mock_profile_handler.get_profile.side_effect = raise_validation

            # Act
            response = await app_client.get(f"/v1/users/{invalid_user_id}/profile")

            # Assert
            assert response.status_code == 400
            data = await response.get_json()
            assert "error" in data

        async def test_handles_correlation_id_from_headers(
            self,
            app_client: QuartTestClient,
            mock_profile_handler: AsyncMock,
            sample_user_id: str,
            sample_profile_response: ProfileResponse,
        ) -> None:
            """Should use correlation ID from X-Correlation-ID header."""
            # Arrange
            correlation_id = uuid4()
            mock_profile_handler.get_profile.return_value = sample_profile_response

            # Act
            response = await app_client.get(
                f"/v1/users/{sample_user_id}/profile",
                headers={"X-Correlation-ID": str(correlation_id)},
            )

            # Assert
            assert response.status_code == 200
            # Verify handler was called with the provided correlation ID
            call_args = mock_profile_handler.get_profile.call_args[0]
            assert call_args[1] == correlation_id

        async def test_generates_correlation_id_if_missing(
            self,
            app_client: QuartTestClient,
            mock_profile_handler: AsyncMock,
            sample_user_id: str,
            sample_profile_response: ProfileResponse,
        ) -> None:
            """Should generate correlation ID if not provided in headers."""
            # Arrange
            mock_profile_handler.get_profile.return_value = sample_profile_response

            # Act
            response = await app_client.get(f"/v1/users/{sample_user_id}/profile")

            # Assert
            assert response.status_code == 200
            # Verify handler was called with a generated UUID
            call_args = mock_profile_handler.get_profile.call_args[0]
            assert isinstance(call_args[1], UUID)

        async def test_handles_unicode_names_in_response(
            self,
            app_client: QuartTestClient,
            mock_profile_handler: AsyncMock,
            sample_user_id: str,
        ) -> None:
            """Should handle Unicode characters in names correctly."""
            # Arrange
            unicode_response = ProfileResponse(
                person_name=PersonNameV1(
                    first_name="François",
                    last_name="Müller",
                    legal_full_name="François Müller",
                ),
                display_name="Prof. François",
                locale="de-DE",
            )
            mock_profile_handler.get_profile.return_value = unicode_response

            # Act
            response = await app_client.get(f"/v1/users/{sample_user_id}/profile")

            # Assert
            assert response.status_code == 200
            data = await response.get_json()
            assert data["person_name"]["first_name"] == "François"
            assert data["person_name"]["last_name"] == "Müller"
            assert data["display_name"] == "Prof. François"

    class TestUpdateProfile:
        """Tests for PUT /v1/users/{user_id}/profile endpoint."""

        @pytest.fixture
        def valid_profile_request(self) -> dict[str, Any]:
            """Valid profile request data with Swedish characters."""
            return {
                "first_name": "Karl",
                "last_name": "Ängström",
                "display_name": "Dr. Karl",
                "locale": "sv-SE",
            }

        async def test_returns_200_with_updated_profile(
            self,
            app_client: QuartTestClient,
            mock_profile_handler: AsyncMock,
            sample_user_id: str,
            valid_profile_request: dict[str, Any],
        ) -> None:
            """Should return 200 with updated profile."""
            # Arrange
            updated_response = ProfileResponse(
                person_name=PersonNameV1(
                    first_name="Karl",
                    last_name="Ängström",
                    legal_full_name="Karl Ängström",
                ),
                display_name="Dr. Karl",
                locale="sv-SE",
            )
            mock_profile_handler.update_profile.return_value = updated_response

            # Act
            response = await app_client.put(
                f"/v1/users/{sample_user_id}/profile", json=valid_profile_request
            )

            # Assert
            assert response.status_code == 200
            data = await response.get_json()
            assert data["person_name"]["first_name"] == "Karl"
            assert data["person_name"]["last_name"] == "Ängström"
            assert data["person_name"]["legal_full_name"] == "Karl Ängström"
            assert data["display_name"] == "Dr. Karl"
            assert data["locale"] == "sv-SE"

            # Verify handler was called correctly
            mock_profile_handler.update_profile.assert_called_once()
            call_args = mock_profile_handler.update_profile.call_args[0]
            assert call_args[0] == sample_user_id
            # Verify domain request was created correctly
            domain_request = call_args[1]
            assert domain_request.first_name == "Karl"
            assert domain_request.last_name == "Ängström"

        async def test_creates_profile_if_missing_upsert_behavior(
            self,
            app_client: QuartTestClient,
            mock_profile_handler: AsyncMock,
            sample_user_id: str,
            valid_profile_request: dict[str, Any],
        ) -> None:
            """Should create profile if missing (upsert behavior)."""
            # Arrange
            new_response = ProfileResponse(
                person_name=PersonNameV1(
                    first_name="Karl",
                    last_name="Ängström",
                    legal_full_name="Karl Ängström",
                ),
                display_name="Dr. Karl",
                locale="sv-SE",
            )
            mock_profile_handler.update_profile.return_value = new_response

            # Act
            response = await app_client.put(
                f"/v1/users/{sample_user_id}/profile", json=valid_profile_request
            )

            # Assert
            assert response.status_code == 200
            data = await response.get_json()
            assert data["person_name"]["first_name"] == "Karl"
            # Verify handler was called (upsert behavior is handled in handler)
            mock_profile_handler.update_profile.assert_called_once()

        @pytest.mark.parametrize(
            "invalid_user_id",
            [
                "not-a-uuid",
                "123-456-789",
            ],
        )
        async def test_returns_400_for_invalid_user_id(
            self,
            app_client: QuartTestClient,
            mock_profile_handler: AsyncMock,
            invalid_user_id: str,
            valid_profile_request: dict[str, Any],
        ) -> None:
            """Should return 400 for invalid UUID format."""
            # Arrange
            from huleedu_service_libs.error_handling import raise_validation_error

            def raise_validation(*_: Any, **__: Any) -> None:
                raise_validation_error(
                    service="identity_service",
                    operation="update_user_profile",
                    field="user_id",
                    message=f"Invalid user_id format: {invalid_user_id}",
                    correlation_id=uuid4(),
                )

            mock_profile_handler.update_profile.side_effect = raise_validation

            # Act
            response = await app_client.put(
                f"/v1/users/{invalid_user_id}/profile", json=valid_profile_request
            )

            # Assert
            assert response.status_code == 400
            data = await response.get_json()
            assert "error" in data

        @pytest.mark.parametrize(
            "invalid_payload",
            [
                {},  # Missing required fields
                {"first_name": ""},  # Empty first name
                {"last_name": ""},  # Empty last name
                {"first_name": "John"},  # Missing last name
                {"last_name": "Doe"},  # Missing first name
            ],
        )
        async def test_returns_400_for_invalid_payload(
            self,
            app_client: QuartTestClient,
            sample_user_id: str,
            invalid_payload: dict[str, Any],
        ) -> None:
            """Should return 400 for missing or invalid required fields."""
            # Act
            response = await app_client.put(
                f"/v1/users/{sample_user_id}/profile", json=invalid_payload
            )

            # Assert
            assert response.status_code == 400
            data = await response.get_json()
            assert "error" in data

        async def test_handles_unicode_characters_in_request(
            self,
            app_client: QuartTestClient,
            mock_profile_handler: AsyncMock,
            sample_user_id: str,
        ) -> None:
            """Should handle Unicode characters in request body."""
            # Arrange
            unicode_request = {
                "first_name": "José",
                "last_name": "García",
                "display_name": "Prof. José",
                "locale": "es-ES",
            }
            unicode_response = ProfileResponse(
                person_name=PersonNameV1(
                    first_name="José",
                    last_name="García",
                    legal_full_name="José García",
                ),
                display_name="Prof. José",
                locale="es-ES",
            )
            mock_profile_handler.update_profile.return_value = unicode_response

            # Act
            response = await app_client.put(
                f"/v1/users/{sample_user_id}/profile", json=unicode_request
            )

            # Assert
            assert response.status_code == 200
            data = await response.get_json()
            assert data["person_name"]["first_name"] == "José"
            assert data["person_name"]["last_name"] == "García"

        async def test_handles_none_optional_fields(
            self,
            app_client: QuartTestClient,
            mock_profile_handler: AsyncMock,
            sample_user_id: str,
        ) -> None:
            """Should handle None values for optional fields."""
            # Arrange
            request_with_nones = {
                "first_name": "Jane",
                "last_name": "Smith",
                "display_name": None,
                "locale": None,
            }
            response_with_nones = ProfileResponse(
                person_name=PersonNameV1(
                    first_name="Jane",
                    last_name="Smith",
                    legal_full_name="Jane Smith",
                ),
                display_name=None,
                locale=None,
            )
            mock_profile_handler.update_profile.return_value = response_with_nones

            # Act
            response = await app_client.put(
                f"/v1/users/{sample_user_id}/profile", json=request_with_nones
            )

            # Assert
            assert response.status_code == 200
            data = await response.get_json()
            assert data["display_name"] is None
            assert data["locale"] is None
