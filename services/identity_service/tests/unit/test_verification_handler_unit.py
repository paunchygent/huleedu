"""
Unit tests for VerificationHandler domain logic behavior.

Tests focus on business logic and behavior rather than implementation details.
Uses protocol-based mocking following established patterns.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from huleedu_service_libs.error_handling import HuleEduError

from services.identity_service.api.schemas import (
    RequestEmailVerificationRequest,
    RequestEmailVerificationResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from services.identity_service.domain_handlers.verification_handler import (
    RequestVerificationResult,
    VerificationHandler,
    VerifyEmailResult,
)
from services.identity_service.protocols import (
    IdentityEventPublisherProtocol,
    UserRepo,
)


class TestVerificationHandler:
    """Tests for VerificationHandler business logic behavior."""

    @pytest.fixture
    def mock_user_repo(self) -> AsyncMock:
        """Create mock user repository following protocol."""
        return AsyncMock(spec=UserRepo)

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher following protocol."""
        return AsyncMock(spec=IdentityEventPublisherProtocol)

    @pytest.fixture
    def handler(
        self,
        mock_user_repo: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> VerificationHandler:
        """Create handler with mocked dependencies."""
        return VerificationHandler(
            user_repo=mock_user_repo,
            event_publisher=mock_event_publisher,
        )

    @pytest.fixture
    def correlation_id(self) -> UUID:
        """Sample correlation ID for testing."""
        return uuid4()

    @pytest.fixture
    def user_id(self) -> str:
        """Sample user ID for testing."""
        return str(uuid4())

    @pytest.fixture
    def sample_user_dict(self, user_id: str) -> dict:
        """Create sample user dict as returned by repository."""
        return {
            "id": user_id,
            "email": "test@example.com",
            "org_id": "test-org",
            "email_verified": False,
        }

    @pytest.fixture
    def verified_user_dict(self, user_id: str) -> dict:
        """Create sample verified user dict."""
        return {
            "id": user_id,
            "email": "verified@example.com",
            "org_id": "test-org",
            "email_verified": True,
        }

    @pytest.fixture
    def swedish_user_dict(self, user_id: str) -> dict:
        """Create sample user dict with Swedish email."""
        return {
            "id": user_id,
            "email": "åsa.öberg@skolan.se",
            "org_id": "swedish-school",
            "email_verified": False,
        }

    @pytest.fixture
    def sample_token_dict(self, user_id: str) -> dict:
        """Create sample token dict as returned by repository."""
        return {
            "id": str(uuid4()),
            "user_id": user_id,
            "token": str(uuid4()),
            "expires_at": datetime.now(UTC) + timedelta(hours=24),
            "used_at": None,
        }

    class TestRequestEmailVerification:
        """Tests for request_email_verification method behavior."""

        @pytest.fixture
        def verification_request(self) -> RequestEmailVerificationRequest:
            """Create valid verification request."""
            return RequestEmailVerificationRequest()

        async def test_successful_verification_request_flow(
            self,
            handler: VerificationHandler,
            mock_user_repo: AsyncMock,
            mock_event_publisher: AsyncMock,
            verification_request: RequestEmailVerificationRequest,
            user_id: str,
            correlation_id: UUID,
            sample_user_dict: dict,
            sample_token_dict: dict,
        ) -> None:
            """Should successfully request verification for unverified user."""
            # Setup: user exists and is unverified
            mock_user_repo.get_user_by_id.return_value = sample_user_dict
            mock_user_repo.create_email_verification_token.return_value = sample_token_dict

            result = await handler.request_email_verification(
                verification_request, user_id, correlation_id
            )

            # Verify return value structure
            assert isinstance(result, RequestVerificationResult)
            assert isinstance(result.response, RequestEmailVerificationResponse)
            assert result.response.message == "Email verification token generated successfully"
            assert result.response.correlation_id == str(correlation_id)

            # Verify repository interactions
            mock_user_repo.get_user_by_id.assert_called_once_with(user_id)
            mock_user_repo.invalidate_user_tokens.assert_called_once_with(user_id)
            mock_user_repo.create_email_verification_token.assert_called_once()

            # Verify token creation parameters
            create_call = mock_user_repo.create_email_verification_token.call_args
            assert create_call[0][0] == user_id  # user_id
            assert isinstance(create_call[0][1], str)  # token (UUID string)
            assert isinstance(create_call[0][2], datetime)  # expires_at

            # Verify event publishing - check call structure but not exact datetime
            mock_event_publisher.publish_email_verification_requested.assert_called_once()
            event_call = mock_event_publisher.publish_email_verification_requested.call_args
            assert event_call[0][0] == sample_user_dict  # user dict

            # The generated token should match what was passed to create_email_verification_token
            generated_token = create_call[0][1]  # token passed to repository
            assert event_call[0][1] == generated_token  # same token passed to event publisher
            assert isinstance(event_call[0][2], datetime)  # expires_at (datetime)
            assert event_call[0][3] == str(correlation_id)  # correlation_id

        async def test_verification_request_with_swedish_email(
            self,
            handler: VerificationHandler,
            mock_user_repo: AsyncMock,
            mock_event_publisher: AsyncMock,
            verification_request: RequestEmailVerificationRequest,
            user_id: str,
            correlation_id: UUID,
            swedish_user_dict: dict,
            sample_token_dict: dict,
        ) -> None:
            """Should handle Swedish characters in email addresses correctly."""
            # Setup
            mock_user_repo.get_user_by_id.return_value = swedish_user_dict
            mock_user_repo.create_email_verification_token.return_value = sample_token_dict

            result = await handler.request_email_verification(
                verification_request, user_id, correlation_id
            )

            # Verify success with Swedish email
            assert isinstance(result, RequestVerificationResult)
            assert result.response.message == "Email verification token generated successfully"

            # Verify event published with Swedish user data
            mock_event_publisher.publish_email_verification_requested.assert_called_once()
            event_call = mock_event_publisher.publish_email_verification_requested.call_args
            assert event_call[0][0] == swedish_user_dict  # user dict with Swedish email

            # Verify that the same generated token was passed to both repository and event publisher
            create_call = mock_user_repo.create_email_verification_token.call_args
            generated_token = create_call[0][1]  # token passed to repository
            assert event_call[0][1] == generated_token  # same token passed to event publisher
            assert isinstance(event_call[0][2], datetime)  # expires_at
            assert event_call[0][3] == str(correlation_id)  # correlation_id

        async def test_verification_request_user_not_found(
            self,
            handler: VerificationHandler,
            mock_user_repo: AsyncMock,
            verification_request: RequestEmailVerificationRequest,
            user_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should raise error when user not found."""
            # Setup: user does not exist
            mock_user_repo.get_user_by_id.return_value = None

            with pytest.raises(HuleEduError):
                await handler.request_email_verification(
                    verification_request, user_id, correlation_id
                )

            # Verify no further operations attempted
            mock_user_repo.invalidate_user_tokens.assert_not_called()
            mock_user_repo.create_email_verification_token.assert_not_called()

        async def test_verification_request_email_already_verified(
            self,
            handler: VerificationHandler,
            mock_user_repo: AsyncMock,
            verification_request: RequestEmailVerificationRequest,
            user_id: str,
            correlation_id: UUID,
            verified_user_dict: dict,
        ) -> None:
            """Should raise error when email already verified."""
            # Setup: user exists but email is verified
            mock_user_repo.get_user_by_id.return_value = verified_user_dict

            with pytest.raises(HuleEduError):
                await handler.request_email_verification(
                    verification_request, user_id, correlation_id
                )

            # Verify no token operations attempted
            mock_user_repo.invalidate_user_tokens.assert_not_called()
            mock_user_repo.create_email_verification_token.assert_not_called()

    class TestVerifyEmail:
        """Tests for verify_email method behavior."""

        @pytest.fixture
        def verification_token(self) -> str:
            """Sample verification token."""
            return str(uuid4())

        @pytest.fixture
        def verify_request(self, verification_token: str) -> VerifyEmailRequest:
            """Create valid verify email request."""
            return VerifyEmailRequest(token=verification_token)

        async def test_successful_email_verification_flow(
            self,
            handler: VerificationHandler,
            mock_user_repo: AsyncMock,
            mock_event_publisher: AsyncMock,
            verify_request: VerifyEmailRequest,
            correlation_id: UUID,
            sample_user_dict: dict,
            sample_token_dict: dict,
        ) -> None:
            """Should successfully verify email with valid token."""
            # Setup: valid token and unverified user
            mock_user_repo.get_email_verification_token.return_value = sample_token_dict
            mock_user_repo.get_user_by_id.return_value = sample_user_dict

            result = await handler.verify_email(verify_request, correlation_id)

            # Verify return value
            assert isinstance(result, VerifyEmailResult)
            assert isinstance(result.response, VerifyEmailResponse)
            assert result.response.message == "Email verified successfully"

            # Verify repository interactions
            mock_user_repo.get_email_verification_token.assert_called_once_with(
                verify_request.token
            )
            mock_user_repo.get_user_by_id.assert_called_once_with(sample_token_dict["user_id"])
            mock_user_repo.mark_token_used.assert_called_once_with(sample_token_dict["id"])
            mock_user_repo.set_email_verified.assert_called_once_with(sample_user_dict["id"])

            # Verify event publishing
            mock_event_publisher.publish_email_verified.assert_called_once_with(
                sample_user_dict, str(correlation_id)
            )

        async def test_verify_email_invalid_token(
            self,
            handler: VerificationHandler,
            mock_user_repo: AsyncMock,
            verify_request: VerifyEmailRequest,
            correlation_id: UUID,
        ) -> None:
            """Should raise error for invalid token."""
            # Setup: token not found
            mock_user_repo.get_email_verification_token.return_value = None

            with pytest.raises(HuleEduError):
                await handler.verify_email(verify_request, correlation_id)

            # Verify no further operations attempted
            mock_user_repo.get_user_by_id.assert_not_called()
            mock_user_repo.mark_token_used.assert_not_called()

        async def test_verify_email_token_already_used(
            self,
            handler: VerificationHandler,
            mock_user_repo: AsyncMock,
            verify_request: VerifyEmailRequest,
            correlation_id: UUID,
            sample_token_dict: dict,
        ) -> None:
            """Should raise error for already used token."""
            # Setup: token is already used
            used_token_dict = sample_token_dict.copy()
            used_token_dict["used_at"] = datetime.now(UTC)
            mock_user_repo.get_email_verification_token.return_value = used_token_dict

            with pytest.raises(HuleEduError):
                await handler.verify_email(verify_request, correlation_id)

            # Verify no user operations attempted
            mock_user_repo.get_user_by_id.assert_not_called()
            mock_user_repo.mark_token_used.assert_not_called()

        async def test_verify_email_expired_token(
            self,
            handler: VerificationHandler,
            mock_user_repo: AsyncMock,
            verify_request: VerifyEmailRequest,
            correlation_id: UUID,
            sample_token_dict: dict,
        ) -> None:
            """Should raise error for expired token."""
            # Setup: token is expired
            expired_token_dict = sample_token_dict.copy()
            expired_token_dict["expires_at"] = datetime.now(UTC) - timedelta(hours=1)
            mock_user_repo.get_email_verification_token.return_value = expired_token_dict

            with pytest.raises(HuleEduError):
                await handler.verify_email(verify_request, correlation_id)

            # Verify no user operations attempted
            mock_user_repo.get_user_by_id.assert_not_called()
            mock_user_repo.mark_token_used.assert_not_called()

        async def test_verify_email_user_not_found(
            self,
            handler: VerificationHandler,
            mock_user_repo: AsyncMock,
            verify_request: VerifyEmailRequest,
            correlation_id: UUID,
            sample_token_dict: dict,
        ) -> None:
            """Should raise error when user not found."""
            # Setup: valid token but user doesn't exist
            mock_user_repo.get_email_verification_token.return_value = sample_token_dict
            mock_user_repo.get_user_by_id.return_value = None

            with pytest.raises(HuleEduError):
                await handler.verify_email(verify_request, correlation_id)

            # Verify no verification operations attempted
            mock_user_repo.mark_token_used.assert_not_called()
            mock_user_repo.set_email_verified.assert_not_called()

        async def test_verify_email_already_verified(
            self,
            handler: VerificationHandler,
            mock_user_repo: AsyncMock,
            verify_request: VerifyEmailRequest,
            correlation_id: UUID,
            sample_token_dict: dict,
            verified_user_dict: dict,
        ) -> None:
            """Should raise error when email already verified."""
            # Setup: valid token but email already verified
            mock_user_repo.get_email_verification_token.return_value = sample_token_dict
            mock_user_repo.get_user_by_id.return_value = verified_user_dict

            with pytest.raises(HuleEduError):
                await handler.verify_email(verify_request, correlation_id)

            # Verify no verification operations attempted
            mock_user_repo.mark_token_used.assert_not_called()
            mock_user_repo.set_email_verified.assert_not_called()
