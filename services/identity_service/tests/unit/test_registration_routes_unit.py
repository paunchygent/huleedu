"""
Unit tests for registration routes in Identity Service.

Tests the POST /v1/auth/register endpoint following the established
Quart+Dishka testing patterns with proper DI mocking and error handling.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, NoReturn
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling.identity_factories import (
    raise_user_already_exists_error,
)
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.identity_service.api.schemas import RegisterResponse
from services.identity_service.app import app
from services.identity_service.domain_handlers.registration_handler import (
    RegistrationHandler,
    RegistrationResult,
)


class TestRegistrationRoutes:
    """Test user registration API endpoint using proper Quart+Dishka patterns."""

    @pytest.fixture
    def mock_registration_handler(self) -> AsyncMock:
        """Create mock registration handler."""
        return AsyncMock(spec=RegistrationHandler)

    @pytest.fixture
    async def app_client(
        self,
        mock_registration_handler: AsyncMock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        """
        Return a Quart test client configured with mocked dependencies using Dishka.
        This fixture overrides production providers with test providers that supply our mocks.
        """

        # 1. Define a test-specific provider that provides our mocks
        class TestProvider(Provider):
            @provide(scope=Scope.REQUEST)
            def provide_registration_handler(self) -> RegistrationHandler:
                return mock_registration_handler

        # 2. Create a new container with our test provider
        container = make_async_container(TestProvider())

        # 3. Apply the container to the app instance for the test
        app.config.update({"TESTING": True})
        QuartDishka(app=app, container=container)

        async with app.test_client() as client:
            yield client

        # 4. Clean up the container after the test
        await container.close()

    async def test_register_success(
        self,
        app_client: QuartTestClient,
        mock_registration_handler: AsyncMock,
    ) -> None:
        """Test successful user registration."""
        # Arrange
        email = "åsa.öberg@skolan.se"  # Swedish characters
        password = "SecureP@ssw0rd123"
        org_id = "school-123"

        registration_response = RegisterResponse(
            user_id="user-456",
            email=email,
            org_id=org_id,
            email_verification_required=True,
        )
        registration_result = RegistrationResult(registration_response)
        mock_registration_handler.register_user.return_value = registration_result

        request_data = {
            "email": email,
            "password": password,
            "person_name": {
                "first_name": "Åsa",
                "last_name": "Öberg",
                "legal_full_name": "Åsa Öberg",
            },
            "organization_name": "Test School",
            "org_id": org_id,
        }

        # Act
        response = await app_client.post(
            "/v1/auth/register",
            json=request_data,
        )

        # Assert
        assert response.status_code == 201
        data = await response.get_json()
        assert data["user_id"] == "user-456"
        assert data["email"] == email
        assert data["org_id"] == org_id
        assert data["email_verification_required"] is True

        # Assert handler was called correctly
        mock_registration_handler.register_user.assert_called_once()
        call_args = mock_registration_handler.register_user.call_args
        register_request = call_args.kwargs["register_request"]
        correlation_id = call_args.kwargs["correlation_id"]

        assert register_request.email == email
        assert register_request.password == password
        assert register_request.org_id == org_id
        assert isinstance(correlation_id, UUID)

    async def test_register_with_correlation_id_header(
        self,
        app_client: QuartTestClient,
        mock_registration_handler: AsyncMock,
    ) -> None:
        """Test registration with custom correlation ID in header."""
        # Arrange
        email = "erik.lundström@university.se"
        password = "TestPassword123!"
        correlation_id_str = "12345678-1234-5678-9abc-123456789abc"

        registration_response = RegisterResponse(
            user_id="user-789",
            email=email,
            org_id=None,
            email_verification_required=True,
        )
        registration_result = RegistrationResult(registration_response)
        mock_registration_handler.register_user.return_value = registration_result

        request_data = {
            "email": email,
            "password": password,
            "person_name": {
                "first_name": "Erik",
                "last_name": "Lundström",
                "legal_full_name": "Erik Lundström",
            },
            "organization_name": "Test University",
        }

        # Act
        response = await app_client.post(
            "/v1/auth/register",
            json=request_data,
            headers={"X-Correlation-ID": correlation_id_str},
        )

        # Assert
        assert response.status_code == 201
        data = await response.get_json()
        assert data["user_id"] == "user-789"
        assert data["email"] == email
        assert data["org_id"] is None

        # Assert handler was called with correct correlation ID
        mock_registration_handler.register_user.assert_called_once()
        call_args = mock_registration_handler.register_user.call_args
        correlation_id = call_args.kwargs["correlation_id"]
        assert str(correlation_id) == correlation_id_str

    async def test_register_invalid_json(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test registration with invalid JSON payload."""
        # Arrange - invalid JSON data
        request_data = {
            "email": "not-an-email",  # Invalid email format
            "password": "pwd",
            "person_name": {
                "first_name": "Test",
                "last_name": "User",
                "legal_full_name": "Test User",
            },
            "organization_name": "Test Org",
        }

        # Act
        response = await app_client.post(
            "/v1/auth/register",
            json=request_data,
        )

        # Assert - Pydantic validation errors are caught as generic exceptions
        # and return 500 due to the current route implementation
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Internal server error"

    async def test_register_user_already_exists(
        self,
        app_client: QuartTestClient,
        mock_registration_handler: AsyncMock,
    ) -> None:
        """Test registration when user already exists."""
        # Arrange
        email = "existing.user@test.com"
        password = "Password123!"
        correlation_id = uuid4()

        def mock_user_exists(*args: Any, **kwargs: Any) -> NoReturn:
            raise_user_already_exists_error(
                service="identity_service",
                operation="register",
                email=email,
                correlation_id=correlation_id,
            )

        mock_registration_handler.register_user.side_effect = mock_user_exists

        request_data = {
            "email": email,
            "password": password,
            "person_name": {
                "first_name": "Existing",
                "last_name": "User",
                "legal_full_name": "Existing User",
            },
            "organization_name": "Existing Org",
        }

        # Act
        response = await app_client.post(
            "/v1/auth/register",
            json=request_data,
        )

        # Assert
        assert response.status_code == 400
        data = await response.get_json()
        # Structured error format from HuleEduError
        error_detail = data["error"]
        assert error_detail["error_code"] == "IDENTITY_USER_ALREADY_EXISTS"
        assert email in error_detail["message"]
        assert error_detail["details"]["email"] == email

    async def test_register_handler_internal_error(
        self,
        app_client: QuartTestClient,
        mock_registration_handler: AsyncMock,
    ) -> None:
        """Test registration when handler raises unexpected error."""
        # Arrange
        email = "test.user@example.com"
        password = "Password123!"

        mock_registration_handler.register_user.side_effect = Exception(
            "Database connection failed"
        )

        request_data = {
            "email": email,
            "password": password,
            "person_name": {
                "first_name": "Test",
                "last_name": "User",
                "legal_full_name": "Test User",
            },
            "organization_name": "Test Organization",
        }

        # Act
        response = await app_client.post(
            "/v1/auth/register",
            json=request_data,
        )

        # Assert
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Internal server error"

    async def test_register_missing_required_fields(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test registration with missing required fields."""
        # Arrange - missing password field
        request_data = {
            "email": "test@example.com",
            # password missing
            "person_name": {
                "first_name": "Test",
                "last_name": "User",
                "legal_full_name": "Test User",
            },
            "organization_name": "Test Organization",
        }

        # Act
        response = await app_client.post(
            "/v1/auth/register",
            json=request_data,
        )

        # Assert - Pydantic validation errors are caught as generic exceptions
        # and return 500 due to the current route implementation
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Internal server error"

    @pytest.mark.parametrize(
        "email, password, org_id",
        [
            # Swedish characters in email and names
            ("åsa.öberg@skolan.se", "Password123!", "school-åäö"),
            ("erik.lindström@universitet.se", "TryggtLösenord456", None),
            ("märta.sjöström@förskolan.se", "Säkert789!", "förskola-123"),
            # Edge cases
            ("user@example.com", "MinimalPwd1!", None),
            ("long.email.address@very-long-domain-name.education", "ComplexP@ssw0rd!", "org-999"),
        ],
    )
    async def test_register_various_inputs(
        self,
        app_client: QuartTestClient,
        mock_registration_handler: AsyncMock,
        email: str,
        password: str,
        org_id: str | None,
    ) -> None:
        """Test registration with various valid input combinations including Swedish characters."""
        # Arrange
        registration_response = RegisterResponse(
            user_id=f"user-{hash(email) % 10000}",
            email=email,
            org_id=org_id,
            email_verification_required=True,
        )
        registration_result = RegistrationResult(registration_response)
        mock_registration_handler.register_user.return_value = registration_result

        request_data = {
            "email": email,
            "password": password,
            "person_name": {
                "first_name": email.split(".")[0].title(),  # Extract from email
                "last_name": email.split(".")[1].split("@")[0].title(),
                "legal_full_name": f"{email.split('.')[0].title()} {email.split('.')[1].split('@')[0].title()}",
            },
            "organization_name": "Test Organization",
        }
        if org_id:
            request_data["org_id"] = org_id

        # Act
        response = await app_client.post(
            "/v1/auth/register",
            json=request_data,
        )

        # Assert
        assert response.status_code == 201
        data = await response.get_json()
        assert data["email"] == email
        assert data["org_id"] == org_id
        assert data["email_verification_required"] is True

        # Assert handler was called with correct parameters
        mock_registration_handler.register_user.assert_called_once()
        call_args = mock_registration_handler.register_user.call_args
        register_request = call_args.kwargs["register_request"]
        assert register_request.email == email
        assert register_request.password == password
        assert register_request.org_id == org_id

        # Reset mock for next iteration
        mock_registration_handler.reset_mock()
