"""Unit tests for Email Service OutboxManager following Rule 075 methodology.

This test suite verifies the transactional outbox pattern implementation
for reliable event publishing in the email service domain.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.emailing_models import EmailDeliveryFailedV1, EmailSentV1
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.outbox.protocols import OutboxRepositoryProtocol
from huleedu_service_libs.redis_client import AtomicRedisClientProtocol

from services.email_service.config import Settings
from huleedu_service_libs.outbox.manager import OutboxManager


@pytest.fixture
def mock_outbox_repository() -> AsyncMock:
    """Mock outbox repository following Protocol specification pattern.

    Returns:
        AsyncMock with OutboxRepositoryProtocol interface.
    """
    mock = AsyncMock(spec=OutboxRepositoryProtocol)
    mock.add_event = AsyncMock(return_value=uuid4())
    return mock


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Mock Redis client for relay worker notification.

    Returns:
        AsyncMock with AtomicRedisClientProtocol interface.
    """
    mock = AsyncMock(spec=AtomicRedisClientProtocol)
    mock.lpush = AsyncMock()
    return mock


@pytest.fixture
def settings() -> Settings:
    """Test settings configuration.

    Returns:
        Email service settings for testing.
    """
    return Settings()


@pytest.fixture
def outbox_manager(
    mock_outbox_repository: AsyncMock, mock_redis_client: AsyncMock
) -> OutboxManager:
    """Create OutboxManager instance with mocked dependencies.

    Args:
        mock_outbox_repository: Mocked outbox repository.
        mock_redis_client: Mocked Redis client.

    Returns:
        OutboxManager instance for testing.
    """
    return OutboxManager(
        outbox_repository=mock_outbox_repository,
        redis_client=mock_redis_client,
        service_name="email_service",
    )


class TestOutboxManager:
    """Test suite for OutboxManager transactional event publishing."""

    @pytest.mark.asyncio
    async def test_publish_email_sent_event_success(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test successful publication of EmailSentV1 event to outbox.

        Verifies that EmailSentV1 events are properly serialized and stored
        in the outbox with correct metadata and envelope structure.
        """
        # Arrange
        correlation_id = uuid4()
        email_sent_data = EmailSentV1(
            message_id="msg-123",
            provider="sendgrid",
            sent_at=datetime(2024, 1, 15, 10, 30, 45),
            correlation_id=str(correlation_id),
        )

        event_envelope: EventEnvelope = EventEnvelope(
            event_type="huleedu.email.sent.v1",
            source_service="email_service",
            correlation_id=correlation_id,
            data=email_sent_data,
            metadata={"email_category": "verification"},
        )

        # Act
        await outbox_manager.publish_to_outbox(
            aggregate_type="email_message",
            aggregate_id="msg-123",
            event_type="huleedu.email.sent.v1",
            event_data=event_envelope,
            topic="huleedu-email-events",
        )

        # Assert - Verify outbox repository was called correctly
        mock_outbox_repository.add_event.assert_called_once()
        call_args = mock_outbox_repository.add_event.call_args

        assert call_args.kwargs["aggregate_id"] == "msg-123"
        assert call_args.kwargs["aggregate_type"] == "email_message"
        assert call_args.kwargs["event_type"] == "huleedu.email.sent.v1"
        assert call_args.kwargs["topic"] == "huleedu-email-events"
        assert call_args.kwargs["event_key"] == "msg-123"

        # Verify event data serialization includes topic
        event_data_arg = call_args.kwargs["event_data"]
        assert event_data_arg["topic"] == "huleedu-email-events"
        assert event_data_arg["event_type"] == "huleedu.email.sent.v1"
        assert event_data_arg["source_service"] == "email_service"
        assert event_data_arg["data"]["message_id"] == "msg-123"
        assert event_data_arg["data"]["provider"] == "sendgrid"

        # Verify Redis notification was sent
        mock_redis_client.lpush.assert_called_once_with("outbox:wake:email_service", "wake")

    @pytest.mark.asyncio
    async def test_publish_email_delivery_failed_event_success(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
    ) -> None:
        """Test successful publication of EmailDeliveryFailedV1 event to outbox.

        Verifies that email delivery failure events are properly handled
        and stored with appropriate error context.
        """
        # Arrange
        correlation_id = uuid4()
        delivery_failed_data = EmailDeliveryFailedV1(
            message_id="msg-456",
            provider="ses",
            failed_at=datetime(2024, 1, 15, 11, 45, 30),
            reason="Invalid recipient email address",
            correlation_id=str(correlation_id),
        )

        event_envelope: EventEnvelope = EventEnvelope(
            event_type="huleedu.email.delivery_failed.v1",
            source_service="email_service",
            correlation_id=correlation_id,
            data=delivery_failed_data,
        )

        # Act
        await outbox_manager.publish_to_outbox(
            aggregate_type="email_message",
            aggregate_id="msg-456",
            event_type="huleedu.email.delivery_failed.v1",
            event_data=event_envelope,
            topic="huleedu-email-events",
        )

        # Assert - Verify event data structure
        call_args = mock_outbox_repository.add_event.call_args
        event_data_arg = call_args.kwargs["event_data"]

        assert event_data_arg["data"]["message_id"] == "msg-456"
        assert event_data_arg["data"]["provider"] == "ses"
        assert event_data_arg["data"]["reason"] == "Invalid recipient email address"
        assert event_data_arg["correlation_id"] == str(correlation_id)

    @pytest.mark.asyncio
    async def test_publish_event_with_custom_partition_key(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
    ) -> None:
        """Test event publication respects custom partition key from metadata.

        Verifies that partition keys specified in event metadata are used
        for Kafka event ordering and distribution.
        """
        # Arrange
        correlation_id = uuid4()
        custom_partition_key = "teacher-12345"

        event_envelope: EventEnvelope = EventEnvelope(
            event_type="huleedu.email.sent.v1",
            source_service="email_service",
            correlation_id=correlation_id,
            data=EmailSentV1(
                message_id="msg-789",
                provider="sendgrid",
                sent_at=datetime(2024, 1, 15, 14, 20, 10),
                correlation_id=str(correlation_id),
            ),
            metadata={"partition_key": custom_partition_key},
        )

        # Act
        await outbox_manager.publish_to_outbox(
            aggregate_type="email_message",
            aggregate_id="msg-789",
            event_type="huleedu.email.sent.v1",
            event_data=event_envelope,
            topic="huleedu-email-events",
        )

        # Assert - Verify custom partition key is used
        call_args = mock_outbox_repository.add_event.call_args
        assert call_args.kwargs["event_key"] == custom_partition_key

    @pytest.mark.asyncio
    async def test_publish_event_with_swedish_characters(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
    ) -> None:
        """Test Swedish character preservation in event data (åäöÅÄÖ).

        Verifies that Swedish characters in email data are properly
        serialized and preserved through the outbox pattern.
        """
        # Arrange
        correlation_id = uuid4()
        swedish_message_id = "msg-åäö-ÅÄÖ-123"

        event_envelope: EventEnvelope = EventEnvelope(
            event_type="huleedu.email.sent.v1",
            source_service="email_service",
            correlation_id=correlation_id,
            data=EmailSentV1(
                message_id=swedish_message_id,
                provider="sendgrid",
                sent_at=datetime(2024, 1, 15, 15, 45, 20),
                correlation_id=str(correlation_id),
            ),
            metadata={"recipient_name": "Åsa Lindström", "school": "Göteborgs Högskola"},
        )

        # Act
        await outbox_manager.publish_to_outbox(
            aggregate_type="email_message",
            aggregate_id=swedish_message_id,
            event_type="huleedu.email.sent.v1",
            event_data=event_envelope,
            topic="huleedu-email-events",
        )

        # Assert - Verify Swedish characters are preserved
        call_args = mock_outbox_repository.add_event.call_args
        event_data_arg = call_args.kwargs["event_data"]

        assert call_args.kwargs["aggregate_id"] == swedish_message_id
        assert event_data_arg["data"]["message_id"] == swedish_message_id
        assert event_data_arg["metadata"]["recipient_name"] == "Åsa Lindström"
        assert event_data_arg["metadata"]["school"] == "Göteborgs Högskola"

    @pytest.mark.asyncio
    async def test_publish_event_correlation_id_propagation(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
    ) -> None:
        """Test correlation ID propagation through event publishing pipeline.

        Verifies that correlation IDs are properly maintained from
        input event through outbox storage for request tracing.
        """
        # Arrange
        original_correlation_id = uuid4()

        event_envelope: EventEnvelope = EventEnvelope(
            event_type="huleedu.email.sent.v1",
            source_service="email_service",
            correlation_id=original_correlation_id,
            data=EmailSentV1(
                message_id="msg-correlation-test",
                provider="mock",
                sent_at=datetime(2024, 1, 15, 16, 30, 40),
                correlation_id=str(original_correlation_id),
            ),
        )

        # Act
        await outbox_manager.publish_to_outbox(
            aggregate_type="email_message",
            aggregate_id="msg-correlation-test",
            event_type="huleedu.email.sent.v1",
            event_data=event_envelope,
            topic="huleedu-email-events",
        )

        # Assert - Verify correlation ID preservation
        call_args = mock_outbox_repository.add_event.call_args
        event_data_arg = call_args.kwargs["event_data"]

        assert event_data_arg["correlation_id"] == str(original_correlation_id)
        assert event_data_arg["data"]["correlation_id"] == str(original_correlation_id)

    @pytest.mark.asyncio
    async def test_publish_event_different_email_categories(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
    ) -> None:
        """Test event publishing for different email categories.

        Verifies that various email types (verification, password_reset, etc.)
        are handled consistently through the outbox pattern.
        """
        # Arrange - Test different email categories
        test_cases = [
            ("verification", "msg-verify-123"),
            ("password_reset", "msg-reset-456"),
            ("teacher_notification", "msg-teacher-789"),
            ("system", "msg-system-012"),
        ]

        for category, message_id in test_cases:
            correlation_id = uuid4()

            event_envelope: EventEnvelope = EventEnvelope(
                event_type="huleedu.email.sent.v1",
                source_service="email_service",
                correlation_id=correlation_id,
                data=EmailSentV1(
                    message_id=message_id,
                    provider="sendgrid",
                    sent_at=datetime(2024, 1, 15, 12, 0, 0),
                    correlation_id=str(correlation_id),
                ),
                metadata={"email_category": category},
            )

            # Act
            await outbox_manager.publish_to_outbox(
                aggregate_type="email_message",
                aggregate_id=message_id,
                event_type="huleedu.email.sent.v1",
                event_data=event_envelope,
                topic="huleedu-email-events",
            )

        # Assert - Verify all categories were processed
        assert mock_outbox_repository.add_event.call_count == len(test_cases)

    @pytest.mark.asyncio
    async def test_publish_event_outbox_repository_not_configured(
        self,
        mock_redis_client: AsyncMock,
        settings: Settings,
    ) -> None:
        """Test error handling when outbox repository is not configured.

        Verifies that proper HuleEduError is raised when attempting
        to publish events without a configured outbox repository.
        """
        # Arrange
        outbox_manager = OutboxManager(
            outbox_repository=None,  # type: ignore[arg-type]
            redis_client=mock_redis_client,
            service_name="email_service",
        )

        correlation_id = uuid4()
        event_envelope: EventEnvelope = EventEnvelope(
            event_type="huleedu.email.sent.v1",
            source_service="email_service",
            correlation_id=correlation_id,
            data=EmailSentV1(
                message_id="msg-no-repo",
                provider="mock",
                sent_at=datetime(2024, 1, 15, 13, 15, 25),
                correlation_id=str(correlation_id),
            ),
        )

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="email_message",
                aggregate_id="msg-no-repo",
                event_type="huleedu.email.sent.v1",
                event_data=event_envelope,
                topic="huleedu-email-events",
            )

        error = exc_info.value
        assert "Outbox repository not configured" in str(error)
        assert error.error_detail.service == "email_service"
        assert error.error_detail.operation == "publish_to_outbox"
        assert error.error_detail.details["external_service"] == "outbox_repository"

    @pytest.mark.asyncio
    async def test_publish_event_invalid_event_data_type(
        self,
        outbox_manager: OutboxManager,
    ) -> None:
        """Test error handling for non-Pydantic event data.

        Verifies that proper error is raised when attempting to publish
        events with invalid data types that cannot be serialized.
        """
        # Arrange
        invalid_event_data = {"not": "a pydantic model"}  # Plain dict instead of EventEnvelope

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="email_message",
                aggregate_id="msg-invalid",
                event_type="huleedu.email.sent.v1",
                event_data=invalid_event_data,  # type: ignore[arg-type]
                topic="huleedu-email-events",
            )

        error = exc_info.value
        assert "Failed to store event in outbox" in str(error)

    @pytest.mark.asyncio
    async def test_publish_event_repository_storage_failure(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
    ) -> None:
        """Test error handling when outbox repository storage fails.

        Verifies that repository failures are properly wrapped in
        HuleEduError with appropriate context and correlation ID.
        """
        # Arrange
        mock_outbox_repository.add_event.side_effect = Exception("Database connection failed")

        correlation_id = uuid4()
        event_envelope: EventEnvelope = EventEnvelope(
            event_type="huleedu.email.sent.v1",
            source_service="email_service",
            correlation_id=correlation_id,
            data=EmailSentV1(
                message_id="msg-db-error",
                provider="sendgrid",
                sent_at=datetime(2024, 1, 15, 17, 45, 50),
                correlation_id=str(correlation_id),
            ),
        )

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="email_message",
                aggregate_id="msg-db-error",
                event_type="huleedu.email.sent.v1",
                event_data=event_envelope,
                topic="huleedu-email-events",
            )

        error = exc_info.value
        assert "Failed to store event in outbox" in str(error)
        assert error.error_detail.service == "email_service"
        assert error.error_detail.operation == "publish_to_outbox"
        assert error.error_detail.correlation_id == correlation_id

    @pytest.mark.asyncio
    async def test_redis_notification_integration_success(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test relay worker notification is sent during event publishing.

        Verifies that Redis wake-up notifications are sent automatically
        when events are published to enable immediate event processing.
        """
        # Arrange
        correlation_id = uuid4()
        event_envelope: EventEnvelope = EventEnvelope(
            event_type="huleedu.email.sent.v1",
            source_service="email_service",
            correlation_id=correlation_id,
            data=EmailSentV1(
                message_id="msg-redis-test",
                provider="sendgrid",
                sent_at=datetime(2024, 1, 15, 10, 30, 45),
                correlation_id=str(correlation_id),
            ),
        )

        # Act
        await outbox_manager.publish_to_outbox(
            aggregate_type="email_message",
            aggregate_id="msg-redis-test",
            event_type="huleedu.email.sent.v1",
            event_data=event_envelope,
            topic="huleedu-email-events",
        )

        # Assert
        mock_redis_client.lpush.assert_called_once_with("outbox:wake:email_service", "wake")

    @pytest.mark.asyncio
    async def test_redis_notification_failure_graceful(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test graceful handling of Redis notification failures during publishing.

        Verifies that Redis notification failures do not raise exceptions
        and allow the outbox pattern to continue functioning via polling.
        """
        # Arrange
        mock_redis_client.lpush.side_effect = Exception("Redis connection timeout")

        correlation_id = uuid4()
        event_envelope: EventEnvelope = EventEnvelope(
            event_type="huleedu.email.sent.v1",
            source_service="email_service",
            correlation_id=correlation_id,
            data=EmailSentV1(
                message_id="msg-redis-error-test",
                provider="sendgrid",
                sent_at=datetime(2024, 1, 15, 10, 30, 45),
                correlation_id=str(correlation_id),
            ),
        )

        # Act - Should not raise exception even if Redis fails
        await outbox_manager.publish_to_outbox(
            aggregate_type="email_message",
            aggregate_id="msg-redis-error-test",
            event_type="huleedu.email.sent.v1",
            event_data=event_envelope,
            topic="huleedu-email-events",
        )

        # Assert - Event should still be stored in outbox despite Redis failure
        mock_outbox_repository.add_event.assert_called_once()
        mock_redis_client.lpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_event_envelope_metadata_preservation(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
    ) -> None:
        """Test EventEnvelope metadata preservation during serialization.

        Verifies that complex metadata structures are properly serialized
        and preserved through the outbox publishing process.
        """
        # Arrange
        correlation_id = uuid4()
        complex_metadata = {
            "user_id": "user-123",
            "tenant_id": "hule-edu-prod",
            "email_category": "teacher_notification",
            "template_version": "2.1.0",
            "localization": "sv-SE",
            "priority": "high",
            "nested_data": {
                "course": "Svenska 1",
                "assignment": "Uppsats om Strindberg",
                "due_date": "2024-02-15",
            },
        }

        event_envelope: EventEnvelope = EventEnvelope(
            event_type="huleedu.email.sent.v1",
            source_service="email_service",
            correlation_id=correlation_id,
            data=EmailSentV1(
                message_id="msg-metadata-test",
                provider="sendgrid",
                sent_at=datetime(2024, 1, 15, 18, 30, 15),
                correlation_id=str(correlation_id),
            ),
            metadata=complex_metadata,
        )

        # Act
        await outbox_manager.publish_to_outbox(
            aggregate_type="email_message",
            aggregate_id="msg-metadata-test",
            event_type="huleedu.email.sent.v1",
            event_data=event_envelope,
            topic="huleedu-email-events",
        )

        # Assert - Verify complex metadata structure is preserved
        call_args = mock_outbox_repository.add_event.call_args
        event_data_arg = call_args.kwargs["event_data"]

        assert event_data_arg["metadata"]["user_id"] == "user-123"
        assert event_data_arg["metadata"]["localization"] == "sv-SE"
        assert event_data_arg["metadata"]["nested_data"]["course"] == "Svenska 1"
        assert event_data_arg["metadata"]["nested_data"]["assignment"] == "Uppsats om Strindberg"

    @pytest.mark.asyncio
    async def test_publish_event_aggregate_type_assignment(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
    ) -> None:
        """Test proper aggregate type assignment for email events.

        Verifies that email domain events are properly categorized
        with correct aggregate types for domain-driven design compliance.
        """
        # Arrange
        test_cases = [
            ("email_message", "msg-001"),
            ("email_template", "template-002"),
            ("email_batch", "batch-003"),
        ]

        for aggregate_type, aggregate_id in test_cases:
            correlation_id = uuid4()

            event_envelope: EventEnvelope = EventEnvelope(
                event_type="huleedu.email.sent.v1",
                source_service="email_service",
                correlation_id=correlation_id,
                data=EmailSentV1(
                    message_id=aggregate_id,
                    provider="mock",
                    sent_at=datetime(2024, 1, 15, 19, 0, 0),
                    correlation_id=str(correlation_id),
                ),
            )

            # Act
            await outbox_manager.publish_to_outbox(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type="huleedu.email.sent.v1",
                event_data=event_envelope,
                topic="huleedu-email-events",
            )

        # Assert - Verify each aggregate type was used correctly
        assert mock_outbox_repository.add_event.call_count == len(test_cases)
        for i, (expected_type, expected_id) in enumerate(test_cases):
            call_args = mock_outbox_repository.add_event.call_args_list[i]
            assert call_args.kwargs["aggregate_type"] == expected_type
            assert call_args.kwargs["aggregate_id"] == expected_id
