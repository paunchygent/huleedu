"""
Unit tests for RegistrationHandler domain logic behavior.

Tests focus on business logic and behavior rather than implementation details.
Uses protocol-based mocking following established patterns.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from huleedu_service_libs.error_handling import HuleEduError

from services.identity_service.api.schemas import (
    RegisterRequest,
    RegisterResponse,
)
from services.identity_service.domain_handlers.registration_handler import (
    RegistrationHandler,
    RegistrationResult,
)
from services.identity_service.protocols import (
    IdentityEventPublisherProtocol,
    PasswordHasher,
    UserRepo,
)


class TestRegistrationHandler:
    """Tests for RegistrationHandler business logic behavior."""

    @pytest.fixture
    def mock_user_repo(self) -> AsyncMock:
        """Create mock user repository following protocol."""
        return AsyncMock(spec=UserRepo)

    @pytest.fixture
    def mock_password_hasher(self) -> AsyncMock:
        """Create mock password hasher following protocol."""
        return AsyncMock(spec=PasswordHasher)

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher following protocol."""
        return AsyncMock(spec=IdentityEventPublisherProtocol)

    @pytest.fixture
    def handler(
        self,
        mock_user_repo: AsyncMock,
        mock_password_hasher: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> RegistrationHandler:
        """Create handler with mocked dependencies."""
        return RegistrationHandler(
            user_repo=mock_user_repo,
            password_hasher=mock_password_hasher,
            event_publisher=mock_event_publisher,
        )

    @pytest.fixture
    def correlation_id(self) -> UUID:
        """Sample correlation ID for testing."""
        return uuid4()

    @pytest.fixture
    def sample_user_dict(self) -> dict:
        """Create sample user dict as returned by repository."""
        return {
            "id": str(uuid4()),
            "email": "test@example.com",
            "org_id": "test-org",
            "email_verification_required": True,
        }

    class TestRegister:
        """Tests for register_user method behavior."""

        @pytest.fixture
        def valid_register_request(self) -> RegisterRequest:
            """Create valid registration request."""
            return RegisterRequest(
                email="test@example.com",
                password="SecurePass123!",
                org_id="test-org",
            )

        @pytest.fixture
        def swedish_register_request(self) -> RegisterRequest:
            """Create registration request with Swedish characters in email domain."""
            return RegisterRequest(
                email="åsa.öberg@skolan.se",
                password="SecurePass123!",
                org_id="swedish-school",
            )

        async def test_successful_registration_flow(
            self,
            handler: RegistrationHandler,
            mock_user_repo: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_event_publisher: AsyncMock,
            valid_register_request: RegisterRequest,
            correlation_id: UUID,
            sample_user_dict: dict,
        ) -> None:
            """Should successfully register new user with complete flow."""
            # Setup: no existing user, successful creation
            mock_user_repo.get_user_by_email.return_value = None
            mock_password_hasher.hash.return_value = "hashed_password_123"
            mock_user_repo.create_user.return_value = sample_user_dict

            result = await handler.register_user(valid_register_request, correlation_id)

            # Verify return value
            assert isinstance(result, RegistrationResult)
            assert isinstance(result.response, RegisterResponse)
            assert result.response.user_id == sample_user_dict["id"]
            assert str(result.response.email) == sample_user_dict["email"]
            assert result.response.org_id == sample_user_dict["org_id"]
            assert result.response.email_verification_required is True

            # Verify repository interactions
            mock_user_repo.get_user_by_email.assert_called_once_with(valid_register_request.email)
            mock_user_repo.create_user.assert_called_once_with(
                valid_register_request.email,
                valid_register_request.org_id,
                "hashed_password_123",
            )

            # Verify password hashing
            mock_password_hasher.hash.assert_called_once_with(valid_register_request.password)

            # Verify event publishing
            mock_event_publisher.publish_user_registered.assert_called_once_with(
                sample_user_dict, str(correlation_id)
            )

        async def test_registration_with_swedish_characters(
            self,
            handler: RegistrationHandler,
            mock_user_repo: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_event_publisher: AsyncMock,
            swedish_register_request: RegisterRequest,
            correlation_id: UUID,
        ) -> None:
            """Should handle Swedish characters in email addresses correctly."""
            swedish_user_dict = {
                "id": str(uuid4()),
                "email": "åsa.öberg@skolan.se",
                "org_id": "swedish-school",
                "email_verification_required": True,
            }

            mock_user_repo.get_user_by_email.return_value = None
            mock_password_hasher.hash.return_value = "hashed_password_456"
            mock_user_repo.create_user.return_value = swedish_user_dict

            result = await handler.register_user(swedish_register_request, correlation_id)

            assert isinstance(result, RegistrationResult)
            assert str(result.response.email) == "åsa.öberg@skolan.se"
            assert result.response.org_id == "swedish-school"

            # Verify Swedish email passed correctly to repository
            mock_user_repo.get_user_by_email.assert_called_once_with("åsa.öberg@skolan.se")

        async def test_raises_error_when_user_already_exists(
            self,
            handler: RegistrationHandler,
            mock_user_repo: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_event_publisher: AsyncMock,
            valid_register_request: RegisterRequest,
            correlation_id: UUID,
            sample_user_dict: dict,
        ) -> None:
            """Should raise HuleEduError when user with email already exists."""
            # Setup: existing user found
            mock_user_repo.get_user_by_email.return_value = sample_user_dict

            with pytest.raises(HuleEduError) as exc_info:
                await handler.register_user(valid_register_request, correlation_id)

            error = exc_info.value
            assert "already exists" in str(error)
            assert str(valid_register_request.email) in str(error)

            # Verify no user creation attempted
            mock_user_repo.create_user.assert_not_called()
            mock_password_hasher.hash.assert_not_called()
            mock_event_publisher.publish_user_registered.assert_not_called()

        async def test_handles_none_org_id(
            self,
            handler: RegistrationHandler,
            mock_user_repo: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_event_publisher: AsyncMock,
            correlation_id: UUID,
        ) -> None:
            """Should handle None org_id in registration request."""
            request = RegisterRequest(
                email="freelancer@example.com",
                password="SecurePass789!",
                org_id=None,
            )

            user_dict_no_org = {
                "id": str(uuid4()),
                "email": "freelancer@example.com",
                "org_id": None,
                "email_verification_required": True,
            }

            mock_user_repo.get_user_by_email.return_value = None
            mock_password_hasher.hash.return_value = "hashed_password_789"
            mock_user_repo.create_user.return_value = user_dict_no_org

            result = await handler.register_user(request, correlation_id)

            assert result.response.org_id is None

            # Verify None org_id passed to create_user
            mock_user_repo.create_user.assert_called_once_with(
                request.email,
                None,
                "hashed_password_789",
            )

        @pytest.mark.parametrize(
            "email, org_id, password",
            [
                ("user@example.com", "org1", "Pass123!"),
                ("åsa.öberg@skolan.se", "swedish-org", "Lösenord456!"),
                ("test+tag@domain.co.uk", None, "Complex_Pass_789"),
                ("user.name@subdomain.example.org", "multi-word-org", "AnotherPass!"),
            ],
        )
        async def test_registration_with_various_email_formats(
            self,
            handler: RegistrationHandler,
            mock_user_repo: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_event_publisher: AsyncMock,
            correlation_id: UUID,
            email: str,
            org_id: str | None,
            password: str,
        ) -> None:
            """Should handle various valid email formats and organization IDs."""
            request = RegisterRequest(
                email=email,
                password=password,
                org_id=org_id,
            )

            user_dict = {
                "id": str(uuid4()),
                "email": email,
                "org_id": org_id,
                "email_verification_required": True,
            }

            mock_user_repo.get_user_by_email.return_value = None
            mock_password_hasher.hash.return_value = f"hashed_{password}"
            mock_user_repo.create_user.return_value = user_dict

            result = await handler.register_user(request, correlation_id)

            assert str(result.response.email) == email
            assert result.response.org_id == org_id

            mock_password_hasher.hash.assert_called_once_with(password)

        async def test_password_hashing_integration(
            self,
            handler: RegistrationHandler,
            mock_user_repo: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_event_publisher: AsyncMock,
            valid_register_request: RegisterRequest,
            correlation_id: UUID,
            sample_user_dict: dict,
        ) -> None:
            """Should properly integrate password hashing in registration flow."""
            mock_user_repo.get_user_by_email.return_value = None
            mock_password_hasher.hash.return_value = "bcrypt_hashed_secure_password"
            mock_user_repo.create_user.return_value = sample_user_dict

            await handler.register_user(valid_register_request, correlation_id)

            # Verify password hasher called with exact password
            mock_password_hasher.hash.assert_called_once_with("SecurePass123!")

            # Verify create_user called with hashed password
            call_args = mock_user_repo.create_user.call_args[0]
            assert call_args[2] == "bcrypt_hashed_secure_password"

        async def test_event_publishing_with_correlation_id(
            self,
            handler: RegistrationHandler,
            mock_user_repo: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_event_publisher: AsyncMock,
            valid_register_request: RegisterRequest,
            correlation_id: UUID,
            sample_user_dict: dict,
        ) -> None:
            """Should publish user registered event with proper correlation ID."""
            mock_user_repo.get_user_by_email.return_value = None
            mock_password_hasher.hash.return_value = "hashed_password"
            mock_user_repo.create_user.return_value = sample_user_dict

            await handler.register_user(valid_register_request, correlation_id)

            # Verify event published with exact parameters
            mock_event_publisher.publish_user_registered.assert_called_once_with(
                sample_user_dict, str(correlation_id)
            )

        async def test_result_to_dict_serialization(
            self,
            handler: RegistrationHandler,
            mock_user_repo: AsyncMock,
            mock_password_hasher: AsyncMock,
            mock_event_publisher: AsyncMock,
            valid_register_request: RegisterRequest,
            correlation_id: UUID,
            sample_user_dict: dict,
        ) -> None:
            """Should provide proper dictionary serialization for API responses."""
            mock_user_repo.get_user_by_email.return_value = None
            mock_password_hasher.hash.return_value = "hashed_password"
            mock_user_repo.create_user.return_value = sample_user_dict

            result = await handler.register_user(valid_register_request, correlation_id)

            result_dict = result.to_dict()

            assert isinstance(result_dict, dict)
            assert result_dict["user_id"] == sample_user_dict["id"]
            assert result_dict["email"] == sample_user_dict["email"]
            assert result_dict["org_id"] == sample_user_dict["org_id"]
            assert result_dict["email_verification_required"] is True
