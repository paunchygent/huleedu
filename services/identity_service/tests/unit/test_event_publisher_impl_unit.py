"""
Unit tests for DefaultIdentityEventPublisher event publishing behavior.

Tests focus on event envelope creation, OutboxManager interaction, and error handling.
Uses protocol-based mocking following Rule 075 methodology.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.identity_enums import LoginFailureReason
from common_core.identity_models import (
    EmailVerificationRequestedV1,
    EmailVerifiedV1,
    LoginFailedV1,
    LoginSucceededV1,
    PasswordResetCompletedV1,
    PasswordResetRequestedV1,
    UserRegisteredV1,
)
from huleedu_service_libs.error_handling import HuleEduError, create_test_huleedu_error
from huleedu_service_libs.outbox.manager import OutboxManager

from services.identity_service.implementations.event_publisher_impl import (
    DefaultIdentityEventPublisher,
)


class TestDefaultIdentityEventPublisher:
    """Tests for DefaultIdentityEventPublisher business logic behavior."""

    @pytest.fixture
    def mock_outbox_manager(self) -> AsyncMock:
        """Create mock outbox manager following protocol."""
        return AsyncMock(spec=OutboxManager)

    @pytest.fixture
    def event_publisher(self, mock_outbox_manager: AsyncMock) -> DefaultIdentityEventPublisher:
        """Create event publisher with mocked dependencies."""
        return DefaultIdentityEventPublisher(
            outbox_manager=mock_outbox_manager, source_service_name="identity_service"
        )

    @pytest.fixture
    def correlation_id(self) -> str:
        """Generate correlation ID for test scenarios."""
        return str(uuid4())

    @pytest.fixture
    def sample_user_data(self) -> dict:
        """Create sample user data for testing event publishing."""
        return {
            "id": str(uuid4()),
            "email": "test.användare@huledu.se",  # Swedish test email
            "org_id": str(uuid4()),
            "registered_at": datetime.now(UTC),
        }

    @pytest.fixture
    def sample_user_data_no_org(self) -> dict:
        """Create sample user data without org_id for testing."""
        return {
            "id": str(uuid4()),
            "email": "nöorg@huledu.se",  # Swedish characters
            "registered_at": datetime.now(UTC),
        }

    async def test_publish_user_registered_creates_correct_envelope(
        self,
        event_publisher: DefaultIdentityEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_user_data: dict,
        correlation_id: str,
    ) -> None:
        """Test user registration event creates proper envelope and calls outbox manager."""
        # Act
        await event_publisher.publish_user_registered(sample_user_data, correlation_id)

        # Assert outbox manager was called
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        # Verify outbox manager call parameters
        assert call_args.kwargs["aggregate_type"] == "user"
        assert call_args.kwargs["aggregate_id"] == sample_user_data["id"]
        assert call_args.kwargs["event_type"] == topic_name(
            ProcessingEvent.IDENTITY_USER_REGISTERED
        )
        assert call_args.kwargs["topic"] == topic_name(ProcessingEvent.IDENTITY_USER_REGISTERED)

        # Verify event envelope structure
        envelope = call_args.kwargs["event_data"]
        assert isinstance(envelope, EventEnvelope)
        assert envelope.event_type == topic_name(ProcessingEvent.IDENTITY_USER_REGISTERED)
        assert envelope.source_service == "identity_service"

        # Verify event data payload
        assert isinstance(envelope.data, UserRegisteredV1)
        assert envelope.data.user_id == sample_user_data["id"]
        assert envelope.data.email == sample_user_data["email"]
        assert envelope.data.org_id == sample_user_data["org_id"]
        assert envelope.data.correlation_id == correlation_id

    async def test_publish_user_registered_handles_missing_org_id(
        self,
        event_publisher: DefaultIdentityEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_user_data_no_org: dict,
        correlation_id: str,
    ) -> None:
        """Test user registration event handles missing org_id correctly."""
        # Act
        await event_publisher.publish_user_registered(sample_user_data_no_org, correlation_id)

        # Assert
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        envelope = mock_outbox_manager.publish_to_outbox.call_args.kwargs["event_data"]
        assert envelope.data.org_id is None

    async def test_publish_login_succeeded_creates_correct_envelope(
        self,
        event_publisher: DefaultIdentityEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_user_data: dict,
        correlation_id: str,
    ) -> None:
        """Test successful login event creates proper envelope with timestamp."""
        # Act
        await event_publisher.publish_login_succeeded(sample_user_data, correlation_id)

        # Assert outbox manager called correctly
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        # Verify call parameters
        assert call_args.kwargs["aggregate_type"] == "user"
        assert call_args.kwargs["aggregate_id"] == sample_user_data["id"]
        assert call_args.kwargs["event_type"] == topic_name(
            ProcessingEvent.IDENTITY_LOGIN_SUCCEEDED
        )

        # Verify envelope and payload
        envelope = call_args.kwargs["event_data"]
        assert isinstance(envelope.data, LoginSucceededV1)
        assert envelope.data.user_id == sample_user_data["id"]
        assert envelope.data.org_id == sample_user_data["org_id"]
        assert envelope.data.correlation_id == correlation_id
        assert isinstance(envelope.data.timestamp, datetime)

    @pytest.mark.parametrize(
        "email, failure_reason",
        [
            ("failed@huledu.se", LoginFailureReason.INVALID_PASSWORD),
            ("äcklig@test.com", LoginFailureReason.ACCOUNT_LOCKED),  # Swedish character
            ("ölöl@domain.se", LoginFailureReason.EMAIL_UNVERIFIED),  # More Swedish chars
            ("normal@test.com", LoginFailureReason.RATE_LIMIT_EXCEEDED),
        ],
    )
    async def test_publish_login_failed_handles_various_scenarios(
        self,
        event_publisher: DefaultIdentityEventPublisher,
        mock_outbox_manager: AsyncMock,
        correlation_id: str,
        email: str,
        failure_reason: LoginFailureReason,
    ) -> None:
        """Test failed login event handles various failure scenarios and Swedish characters."""
        # Act
        await event_publisher.publish_login_failed(email, failure_reason, correlation_id)

        # Assert
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        # Verify special aggregate handling for failed logins
        assert call_args.kwargs["aggregate_type"] == "login_attempt"
        assert call_args.kwargs["aggregate_id"] == email
        assert call_args.kwargs["event_type"] == topic_name(ProcessingEvent.IDENTITY_LOGIN_FAILED)

        # Verify payload data
        envelope = call_args.kwargs["event_data"]
        assert isinstance(envelope.data, LoginFailedV1)
        assert envelope.data.email == email
        assert envelope.data.reason == failure_reason
        assert envelope.data.correlation_id == correlation_id

    async def test_publish_email_verification_requested_creates_correct_envelope(
        self,
        event_publisher: DefaultIdentityEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_user_data: dict,
        correlation_id: str,
    ) -> None:
        """Test email verification request event includes token details."""
        # Arrange
        verification_token = str(uuid4())
        expires_at = datetime.now(UTC) + timedelta(hours=24)

        # Act
        await event_publisher.publish_email_verification_requested(
            sample_user_data, verification_token, expires_at, correlation_id
        )

        # Assert
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        envelope = mock_outbox_manager.publish_to_outbox.call_args.kwargs["event_data"]

        assert isinstance(envelope.data, EmailVerificationRequestedV1)
        assert envelope.data.user_id == sample_user_data["id"]
        assert envelope.data.email == sample_user_data["email"]
        assert envelope.data.verification_token == verification_token
        assert envelope.data.expires_at == expires_at
        assert envelope.data.correlation_id == correlation_id

    async def test_publish_email_verified_creates_correct_envelope(
        self,
        event_publisher: DefaultIdentityEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_user_data: dict,
        correlation_id: str,
    ) -> None:
        """Test email verification completion event includes verification timestamp."""
        # Act
        await event_publisher.publish_email_verified(sample_user_data, correlation_id)

        # Assert
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        envelope = mock_outbox_manager.publish_to_outbox.call_args.kwargs["event_data"]

        assert isinstance(envelope.data, EmailVerifiedV1)
        assert envelope.data.user_id == sample_user_data["id"]
        assert envelope.data.correlation_id == correlation_id
        assert isinstance(envelope.data.verified_at, datetime)

    async def test_publish_password_reset_requested_creates_correct_envelope(
        self,
        event_publisher: DefaultIdentityEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_user_data: dict,
        correlation_id: str,
    ) -> None:
        """Test password reset request event includes token and expiration details."""
        # Arrange
        token_id = str(uuid4())
        expires_at = datetime.now(UTC) + timedelta(hours=2)

        # Act
        await event_publisher.publish_password_reset_requested(
            sample_user_data, token_id, expires_at, correlation_id
        )

        # Assert
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        assert call_args.kwargs["event_type"] == topic_name(
            ProcessingEvent.IDENTITY_PASSWORD_RESET_REQUESTED
        )

        envelope = call_args.kwargs["event_data"]
        assert isinstance(envelope.data, PasswordResetRequestedV1)
        assert envelope.data.user_id == sample_user_data["id"]
        assert envelope.data.email == sample_user_data["email"]
        assert envelope.data.token_id == token_id
        assert envelope.data.expires_at == expires_at
        assert envelope.data.correlation_id == correlation_id

    async def test_publish_password_reset_completed_creates_correct_envelope(
        self,
        event_publisher: DefaultIdentityEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_user_data: dict,
        correlation_id: str,
    ) -> None:
        """Test password reset completion event includes reset timestamp."""
        # Act
        await event_publisher.publish_password_reset_completed(sample_user_data, correlation_id)

        # Assert
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        envelope = mock_outbox_manager.publish_to_outbox.call_args.kwargs["event_data"]

        assert isinstance(envelope.data, PasswordResetCompletedV1)
        assert envelope.data.user_id == sample_user_data["id"]
        assert envelope.data.correlation_id == correlation_id
        assert isinstance(envelope.data.reset_at, datetime)

    async def test_publish_user_logged_out_does_not_publish_to_outbox(
        self,
        event_publisher: DefaultIdentityEventPublisher,
        mock_outbox_manager: AsyncMock,
        correlation_id: str,
    ) -> None:
        """Test user logout does not publish to outbox (only logs)."""
        # Arrange
        user_id = str(uuid4())

        # Act
        await event_publisher.publish_user_logged_out(user_id, correlation_id)

        # Assert no outbox interaction - focus on behavioral testing
        mock_outbox_manager.publish_to_outbox.assert_not_called()

        # The method should complete successfully without exceptions
        # (Testing behavior: method completes, no outbox publishing)

    async def test_outbox_manager_failure_propagates_error(
        self,
        event_publisher: DefaultIdentityEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_user_data: dict,
        correlation_id: str,
    ) -> None:
        """Test that outbox manager failures are properly propagated as HuleEduError."""
        # Arrange
        mock_outbox_manager.publish_to_outbox.side_effect = create_test_huleedu_error(
            message="Outbox storage failed", service="outbox_manager"
        )

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await event_publisher.publish_user_registered(sample_user_data, correlation_id)

        assert exc_info.value.error_detail.service == "outbox_manager"
        assert "Outbox storage failed" in str(exc_info.value)

    @pytest.mark.parametrize(
        "method_name, args",
        [
            ("publish_user_registered", lambda user, corr_id: (user, corr_id)),
            ("publish_login_succeeded", lambda user, corr_id: (user, corr_id)),
            ("publish_email_verified", lambda user, corr_id: (user, corr_id)),
            ("publish_password_reset_completed", lambda user, corr_id: (user, corr_id)),
        ],
    )
    async def test_all_user_events_use_user_aggregate_type(
        self,
        event_publisher: DefaultIdentityEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_user_data: dict,
        correlation_id: str,
        method_name: str,
        args: Callable,
    ) -> None:
        """Test that all user-related events use 'user' as aggregate_type."""
        # Arrange
        method = getattr(event_publisher, method_name)
        call_args = args(sample_user_data, correlation_id)

        # Act
        await method(*call_args)

        # Assert
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_kwargs = mock_outbox_manager.publish_to_outbox.call_args.kwargs
        assert call_kwargs["aggregate_type"] == "user"
        assert call_kwargs["aggregate_id"] == sample_user_data["id"]

    async def test_correlation_id_propagation_across_all_events(
        self,
        event_publisher: DefaultIdentityEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_user_data: dict,
    ) -> None:
        """Test that correlation_id is properly propagated in all event types."""
        # Arrange
        test_correlation_id = "12345678-1234-5678-9abc-123456789abc"

        # Act - Test each method that should propagate correlation_id
        await event_publisher.publish_user_registered(sample_user_data, test_correlation_id)

        # Reset mock for next call
        mock_outbox_manager.reset_mock()
        await event_publisher.publish_login_succeeded(sample_user_data, test_correlation_id)

        # Assert correlation_id in envelope
        envelope = mock_outbox_manager.publish_to_outbox.call_args.kwargs["event_data"]
        assert envelope.data.correlation_id == test_correlation_id
