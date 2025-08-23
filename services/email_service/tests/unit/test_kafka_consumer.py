"""Unit tests for EmailKafkaConsumer message processing logic.

Tests the EmailKafkaConsumer's _process_message method focusing on:
1. Event deserialization from EmailNotificationRequestedV1 events
2. Idempotency behavior with correlation ID tracking
3. Error handling for malformed messages and processing failures
4. Swedish character support in email addresses (åäöÅÄÖ)
5. Event processor integration through dependency injection

Following Rule 075 methodology with behavioral testing and proper mocking patterns.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiokafka import ConsumerRecord
from common_core.emailing_models import NotificationEmailRequestedV1
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope

from services.email_service.config import Settings
from services.email_service.event_processor import EmailEventProcessor
from services.email_service.kafka_consumer import EmailKafkaConsumer


class MockSettings(Settings):
    """Mock settings for EmailKafkaConsumer testing."""

    def __init__(self) -> None:
        # Initialize with test database URL to satisfy Settings requirements
        super().__init__()
        # Override settings for testing
        object.__setattr__(self, "DEFAULT_FROM_EMAIL", "test@huleedu.se")
        object.__setattr__(self, "DEFAULT_FROM_NAME", "HuleEdu Test")


class MockRedisClient:
    """Mock Redis client for idempotency testing."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int | None]] = []

    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        """Mock Redis SETNX operation."""
        self.set_calls.append((key, value, ttl_seconds))
        if key in self.keys:
            return False
        self.keys[key] = value
        return True

    async def delete_key(self, key: str) -> int:
        """Mock Redis DELETE operation."""
        if key in self.keys:
            del self.keys[key]
            return 1
        return 0

    async def delete(self, *keys: str) -> int:
        """Mock multi-key DELETE operation."""
        total_deleted = 0
        for key in keys:
            deleted_count = await self.delete_key(key)
            total_deleted += deleted_count
        return total_deleted

    async def get(self, key: str) -> str | None:
        """Mock GET operation."""
        return self.keys.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        """Mock SETEX operation."""
        self.keys[key] = value
        return True

    async def ping(self) -> bool:
        """Mock PING operation."""
        return True


def create_kafka_message(envelope: EventEnvelope) -> ConsumerRecord:
    """Create a mock Kafka ConsumerRecord with event envelope.

    Args:
        envelope: EventEnvelope to serialize as JSON

    Returns:
        ConsumerRecord for testing
    """
    return ConsumerRecord(
        topic=topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED),
        partition=0,
        offset=123,
        timestamp=None,
        timestamp_type=None,
        key=None,
        value=envelope.model_dump_json().encode("utf-8"),
        checksum=None,
        serialized_key_size=None,
        serialized_value_size=None,
        headers=[],
    )


def create_valid_email_envelope(
    to_email: str = "test@example.com",
    template_id: str = "verification",
    variables: dict[str, str] | None = None,
    category: str = "verification",
) -> EventEnvelope[NotificationEmailRequestedV1]:
    """Create a valid EmailNotificationRequestedV1 envelope structure.

    Args:
        to_email: Recipient email address
        template_id: Template identifier
        variables: Template variables
        category: Email category

    Returns:
        Event envelope ready for Kafka message
    """
    if variables is None:
        variables = {"name": "Test User", "verification_url": "https://huleedu.se/verify"}

    correlation_id = str(uuid4())
    message_id = str(uuid4())

    event_data = NotificationEmailRequestedV1(
        message_id=message_id,
        template_id=template_id,
        to=to_email,
        variables=variables,
        category=category,
        correlation_id=correlation_id,
    )

    return EventEnvelope[NotificationEmailRequestedV1](
        event_id=uuid4(),
        event_type=topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED),
        event_timestamp=datetime.now(UTC),
        source_service="identity_service",
        correlation_id=uuid4(),
        data=event_data,
    )


class TestEmailKafkaConsumer:
    """Unit tests for EmailKafkaConsumer message processing behavior."""

    @pytest.fixture
    def mock_event_processor(self) -> AsyncMock:
        """Mock EmailEventProcessor for testing behavior."""
        return AsyncMock(spec=EmailEventProcessor)

    @pytest.fixture
    def mock_settings(self) -> MockSettings:
        """Mock Settings for testing."""
        return MockSettings()

    @pytest.fixture
    def mock_redis_client(self) -> MockRedisClient:
        """Mock Redis client for idempotency testing."""
        return MockRedisClient()

    @pytest.fixture
    def kafka_consumer(
        self,
        mock_settings: MockSettings,
        mock_event_processor: AsyncMock,
        mock_redis_client: MockRedisClient,
    ) -> EmailKafkaConsumer:
        """Create EmailKafkaConsumer instance with mocked dependencies."""
        return EmailKafkaConsumer(
            settings=mock_settings,
            event_processor=mock_event_processor,
            redis_client=mock_redis_client,
        )

    @pytest.mark.asyncio
    async def test_process_message_calls_event_processor_with_correct_data(
        self,
        kafka_consumer: EmailKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test that valid messages are processed and passed to event processor correctly."""
        # Arrange
        envelope = create_valid_email_envelope(
            to_email="recipient@huleedu.se",
            template_id="verification",
            variables={"name": "Test User", "verification_url": "https://huleedu.se/verify"},
        )
        kafka_message = create_kafka_message(envelope)

        # Act
        result = await kafka_consumer._process_message(kafka_message)

        # Assert
        assert result is True
        mock_event_processor.process_email_request.assert_called_once()

        # Verify the call arguments match the expected NotificationEmailRequestedV1
        call_args = mock_event_processor.process_email_request.call_args[0][0]
        assert isinstance(call_args, NotificationEmailRequestedV1)
        assert call_args.to == "recipient@huleedu.se"
        assert call_args.template_id == "verification"
        assert call_args.category == "verification"
        assert "name" in call_args.variables
        assert call_args.variables["name"] == "Test User"

    @pytest.mark.asyncio
    async def test_process_message_handles_malformed_json_gracefully(
        self,
        kafka_consumer: EmailKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test that malformed JSON messages return False without crashing."""
        # Arrange - Create message with invalid JSON
        invalid_message = ConsumerRecord(
            topic=topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED),
            partition=0,
            offset=123,
            timestamp=None,
            timestamp_type=None,
            key=None,
            value=b'{"invalid": json, "missing": "quotes"}',
            checksum=None,
            serialized_key_size=None,
            serialized_value_size=None,
            headers=[],
        )

        # Act
        result = await kafka_consumer._process_message(invalid_message)

        # Assert
        assert result is False
        mock_event_processor.process_email_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_handles_invalid_envelope_structure(
        self,
        kafka_consumer: EmailKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test that messages with invalid envelope structure return False."""
        # Arrange - Create message with missing required envelope fields
        invalid_envelope_json = json.dumps(
            {
                "event_id": str(uuid4()),
                # Missing event_type, event_timestamp, etc.
                "data": {"message_id": "test-123"},
            }
        )
        invalid_message = ConsumerRecord(
            topic=topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED),
            partition=0,
            offset=123,
            timestamp=None,
            timestamp_type=None,
            key=None,
            value=invalid_envelope_json.encode("utf-8"),
            checksum=None,
            serialized_key_size=None,
            serialized_value_size=None,
            headers=[],
        )

        # Act
        result = await kafka_consumer._process_message(invalid_message)

        # Assert
        assert result is False
        mock_event_processor.process_email_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_handles_invalid_event_data(
        self,
        kafka_consumer: EmailKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test that messages with invalid NotificationEmailRequestedV1 data return False."""
        # Arrange - Valid envelope but invalid event data
        invalid_envelope_json = json.dumps(
            {
                "event_id": str(uuid4()),
                "event_type": topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED),
                "event_timestamp": datetime.now(UTC).isoformat(),
                "source_service": "test_service",
                "correlation_id": str(uuid4()),
                "data": {
                    "message_id": "test-123",
                    # Missing required fields like 'to', 'template_id', etc.
                    "invalid_field": "should not work",
                },
            }
        )
        invalid_message = ConsumerRecord(
            topic=topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED),
            partition=0,
            offset=123,
            timestamp=None,
            timestamp_type=None,
            key=None,
            value=invalid_envelope_json.encode("utf-8"),
            checksum=None,
            serialized_key_size=None,
            serialized_value_size=None,
            headers=[],
        )

        # Act
        result = await kafka_consumer._process_message(invalid_message)

        # Assert
        assert result is False
        mock_event_processor.process_email_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_handles_event_processor_exception(
        self,
        kafka_consumer: EmailKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test that event processor exceptions are handled gracefully."""
        # Arrange
        mock_event_processor.process_email_request.side_effect = Exception("Processing failed")
        envelope = create_valid_email_envelope()
        kafka_message = create_kafka_message(envelope)

        # Act
        result = await kafka_consumer._process_message(kafka_message)

        # Assert
        assert result is False
        mock_event_processor.process_email_request.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "email_address",
        [
            # Standard cases
            "user@huleedu.se",
            "test.user@example.com",
            "user+tag@domain.org",
            # Swedish character support (åäöÅÄÖ)
            "åsa@huleedu.se",
            "erik.äström@university.se",
            "nils.öberg@school.se",
            "Åke.Lindström@huleedu.se",
            "märta.björk@education.se",
        ],
    )
    async def test_process_message_handles_swedish_characters_in_emails(
        self,
        kafka_consumer: EmailKafkaConsumer,
        mock_event_processor: AsyncMock,
        email_address: str,
    ) -> None:
        """Test that Swedish characters in email addresses are handled correctly."""
        # Arrange
        envelope = create_valid_email_envelope(to_email=email_address)
        kafka_message = create_kafka_message(envelope)

        # Act
        result = await kafka_consumer._process_message(kafka_message)

        # Assert
        assert result is True
        mock_event_processor.process_email_request.assert_called_once()

        # Verify the email address was preserved correctly
        call_args = mock_event_processor.process_email_request.call_args[0][0]
        assert str(call_args.to) == email_address

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "invalid_email",
        [
            "invalid.email",  # Missing @
            "@invalid.com",  # Missing local part
            "user@",  # Missing domain
            "",  # Empty string
            "user@.com",  # Invalid domain
            "user..name@domain.com",  # Double dots
        ],
    )
    async def test_process_message_handles_invalid_email_addresses(
        self,
        kafka_consumer: EmailKafkaConsumer,
        mock_event_processor: AsyncMock,
        invalid_email: str,
    ) -> None:
        """Test that invalid email addresses are handled gracefully."""
        # Arrange - Create envelope manually to bypass Pydantic validation in test setup
        invalid_envelope_json = json.dumps(
            {
                "event_id": str(uuid4()),
                "event_type": topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED),
                "event_timestamp": datetime.now(UTC).isoformat(),
                "source_service": "test_service",
                "correlation_id": str(uuid4()),
                "data": {
                    "message_id": str(uuid4()),
                    "template_id": "verification",
                    "to": invalid_email,  # Invalid email will cause Pydantic validation to fail
                    "variables": {"name": "Test"},
                    "category": "verification",
                    "correlation_id": str(uuid4()),
                },
            }
        )
        invalid_message = ConsumerRecord(
            topic=topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED),
            partition=0,
            offset=123,
            timestamp=None,
            timestamp_type=None,
            key=None,
            value=invalid_envelope_json.encode("utf-8"),
            checksum=None,
            serialized_key_size=None,
            serialized_value_size=None,
            headers=[],
        )

        # Act
        result = await kafka_consumer._process_message(invalid_message)

        # Assert
        assert result is False
        mock_event_processor.process_email_request.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "template_id,category,variables",
        [
            # Standard template cases
            (
                "verification",
                "verification",
                {"name": "Test", "verification_url": "https://huleedu.se"},
            ),
            (
                "password_reset",
                "password_reset",
                {"name": "User", "reset_url": "https://huleedu.se/reset"},
            ),
            ("welcome", "system", {"name": "New User", "login_url": "https://huleedu.se/login"}),
            # Swedish content in variables
            ("welcome", "system", {"name": "Åsa Lindström", "school": "Röda skolan"}),
            (
                "verification",
                "verification",
                {"name": "Erik Äström", "message": "Välkommen till HuleEdu!"},
            ),
        ],
    )
    async def test_process_message_handles_different_template_types(
        self,
        kafka_consumer: EmailKafkaConsumer,
        mock_event_processor: AsyncMock,
        template_id: str,
        category: str,
        variables: dict[str, str],
    ) -> None:
        """Test that different template types and categories are processed correctly."""
        # Arrange
        envelope = create_valid_email_envelope(
            template_id=template_id,
            category=category,
            variables=variables,
        )
        kafka_message = create_kafka_message(envelope)

        # Act
        result = await kafka_consumer._process_message(kafka_message)

        # Assert
        assert result is True
        mock_event_processor.process_email_request.assert_called_once()

        # Verify template and category were preserved
        call_args = mock_event_processor.process_email_request.call_args[0][0]
        assert call_args.template_id == template_id
        assert call_args.category == category
        assert call_args.variables == variables

    @pytest.mark.asyncio
    async def test_process_message_preserves_correlation_id(
        self,
        kafka_consumer: EmailKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test that correlation IDs are properly preserved through processing."""
        # Arrange
        expected_correlation_id = str(uuid4())
        envelope = create_valid_email_envelope()
        # Manually set the data correlation_id to test preservation
        envelope.data.correlation_id = expected_correlation_id
        kafka_message = create_kafka_message(envelope)

        # Act
        result = await kafka_consumer._process_message(kafka_message)

        # Assert
        assert result is True
        mock_event_processor.process_email_request.assert_called_once()

        # Verify correlation ID preservation
        call_args = mock_event_processor.process_email_request.call_args[0][0]
        assert call_args.correlation_id == expected_correlation_id

    @pytest.mark.asyncio
    async def test_idempotent_processing_first_time_success(
        self,
        kafka_consumer: EmailKafkaConsumer,
        mock_event_processor: AsyncMock,
        mock_redis_client: MockRedisClient,
    ) -> None:
        """Test that first-time message processing works with idempotency."""
        # Arrange
        envelope = create_valid_email_envelope()
        kafka_message = create_kafka_message(envelope)

        # Act
        result = await kafka_consumer._process_email_request_idempotently(kafka_message)

        # Assert
        assert result is True
        assert len(mock_redis_client.set_calls) == 1  # Redis lock was acquired
        mock_event_processor.process_email_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_idempotent_processing_duplicate_detection(
        self,
        kafka_consumer: EmailKafkaConsumer,
        mock_event_processor: AsyncMock,
        mock_redis_client: MockRedisClient,
    ) -> None:
        """Test that duplicate messages are properly detected and skipped."""
        # Arrange
        envelope = create_valid_email_envelope()
        kafka_message = create_kafka_message(envelope)

        # Act - Process first time
        result1 = await kafka_consumer._process_email_request_idempotently(kafka_message)

        # Act - Process duplicate
        result2 = await kafka_consumer._process_email_request_idempotently(kafka_message)

        # Assert
        assert result1 is True  # First processing succeeded
        assert result2 is None  # Duplicate was skipped
        assert len(mock_redis_client.set_calls) == 1  # Only one Redis lock attempt
        mock_event_processor.process_email_request.assert_called_once()  # Only called once
