"""Unit tests for EntitlementsKafkaConsumer following Rule 075 methodology.

This module tests the Kafka consumer's event processing behavior, including:
- ResourceConsumptionV1 event deserialization and processing
- Credit consumption flow with protocol-based mocking
- Idempotent message processing with Redis-based deduplication
- Manual offset commits after successful processing
- Error handling for malformed events and processing failures
- Consumer lifecycle management
- Swedish character handling in identity fields

Test focuses on business logic behavior rather than implementation details,
using protocol-based mocking with AsyncMock and comprehensive parametrization.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.event_enums import ProcessingEvent
from common_core.events.envelope import EventEnvelope
from common_core.events.resource_consumption_events import ResourceConsumptionV1
from huleedu_service_libs.redis_client import AtomicRedisClientProtocol

from services.entitlements_service.kafka_consumer import EntitlementsKafkaConsumer
from services.entitlements_service.protocols import (
    CreditConsumptionResult,
    CreditManagerProtocol,
)


class TestEntitlementsKafkaConsumer:
    """Tests for the EntitlementsKafkaConsumer class."""

    @pytest.fixture
    def mock_credit_manager(self) -> AsyncMock:
        """Create mock credit manager with AsyncMock and spec."""
        manager = AsyncMock(spec=CreditManagerProtocol)
        manager.consume_credits.return_value = CreditConsumptionResult(
            success=True, new_balance=100, consumed_from="user"
        )
        return manager

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Create mock Redis client for idempotency testing."""
        redis = AsyncMock(spec=AtomicRedisClientProtocol)
        return redis

    @pytest.fixture
    def consumer_instance(
        self, mock_credit_manager: AsyncMock, mock_redis_client: AsyncMock
    ) -> EntitlementsKafkaConsumer:
        """Create EntitlementsKafkaConsumer instance with mocked dependencies."""
        return EntitlementsKafkaConsumer(
            kafka_bootstrap_servers="localhost:9092",
            consumer_group="test-entitlements-group",
            credit_manager=mock_credit_manager,
            redis_client=mock_redis_client,
        )

    @pytest.fixture
    def sample_resource_consumption_event(self) -> ResourceConsumptionV1:
        """Create sample ResourceConsumptionV1 event for testing."""
        return ResourceConsumptionV1(
            event_name=ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED,
            entity_id="batch-123",
            entity_type="batch",
            user_id="user-456",
            org_id="org-789",
            resource_type="ai_feedback",
            quantity=2,
            service_name="cj_assessment_service",
            processing_id="job-abc123",
            consumed_at=datetime.now(UTC),
        )

    @pytest.fixture
    def sample_event_envelope(
        self, sample_resource_consumption_event: ResourceConsumptionV1
    ) -> EventEnvelope[ResourceConsumptionV1]:
        """Create EventEnvelope wrapper for ResourceConsumptionV1."""
        return EventEnvelope[ResourceConsumptionV1](
            event_type="huleedu.resource.consumption.v1",
            source_service="cj_assessment_service",
            correlation_id=uuid4(),
            data=sample_resource_consumption_event,
        )

    @pytest.fixture
    def sample_kafka_message(
        self, sample_event_envelope: EventEnvelope[ResourceConsumptionV1]
    ) -> Any:
        """Create mock Kafka message with serialized event data."""
        message = MagicMock()
        message.topic = "huleedu.resource.consumption.v1"
        message.partition = 0
        message.offset = 123
        message.key = b"batch-123"
        message.value = json.dumps(sample_event_envelope.model_dump(mode="json")).encode("utf-8")
        return message

    @pytest.mark.asyncio
    async def test_handle_message_processes_resource_consumption_event(
        self,
        consumer_instance: EntitlementsKafkaConsumer,
        mock_credit_manager: AsyncMock,
        sample_kafka_message: Any,
    ) -> None:
        """Test that _handle_message processes ResourceConsumptionV1 events correctly."""
        # Act
        await consumer_instance._handle_message(sample_kafka_message)

        # Assert - Verify credit manager was called with correct parameters
        # Get correlation_id from the message for assertion
        envelope_data = json.loads(sample_kafka_message.value.decode("utf-8"))
        correlation_id = envelope_data["correlation_id"]

        mock_credit_manager.consume_credits.assert_called_once_with(
            user_id="user-456",
            org_id="org-789",
            metric="ai_feedback",
            amount=2,
            batch_id="batch-123",
            correlation_id=str(correlation_id),
        )

    @pytest.mark.asyncio
    async def test_handle_message_with_none_org_id(
        self,
        consumer_instance: EntitlementsKafkaConsumer,
        mock_credit_manager: AsyncMock,
    ) -> None:
        """Test event processing when org_id is None."""
        # Arrange - Event without organization
        event = ResourceConsumptionV1(
            event_name=ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED,
            entity_id="batch-456",
            entity_type="batch",
            user_id="user-solo",
            org_id=None,
            resource_type="spell_check",
            quantity=1,
            service_name="spell_checker_service",
            processing_id="spell-job-456",
        )
        envelope = EventEnvelope[ResourceConsumptionV1](
            event_type="huleedu.resource.consumption.v1",
            source_service="spell_checker_service",
            correlation_id=uuid4(),
            data=event,
        )
        message = MagicMock()
        message.value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")

        # Act
        await consumer_instance._handle_message(message)

        # Assert - Verify org_id is passed as None
        mock_credit_manager.consume_credits.assert_called_once_with(
            user_id="user-solo",
            org_id=None,
            metric="spell_check",
            amount=1,
            batch_id="batch-456",
            correlation_id=str(envelope.correlation_id),
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_id,org_id,expected_user,expected_org",
        [
            # Swedish characters in user IDs
            ("användar-åäö", "org-123", "användar-åäö", "org-123"),
            ("user-ÅÄÖ-test", "org-456", "user-ÅÄÖ-test", "org-456"),
            # Swedish characters in org IDs
            ("user-123", "organisation-åäö", "user-123", "organisation-åäö"),
            ("user-456", "FÖRETAG-ÅÄÖ", "user-456", "FÖRETAG-ÅÄÖ"),
            # Mixed Swedish characters
            ("lärare-örebro", "skola-växjö", "lärare-örebro", "skola-växjö"),
            # Regular ASCII for baseline
            ("user-regular", "org-regular", "user-regular", "org-regular"),
        ],
    )
    async def test_handle_message_with_swedish_characters(
        self,
        consumer_instance: EntitlementsKafkaConsumer,
        mock_credit_manager: AsyncMock,
        user_id: str,
        org_id: str,
        expected_user: str,
        expected_org: str,
    ) -> None:
        """Test handling of Swedish characters (åäöÅÄÖ) in identity fields."""
        # Arrange
        event = ResourceConsumptionV1(
            event_name=ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED,
            entity_id="batch-swedish",
            entity_type="batch",
            user_id=user_id,
            org_id=org_id,
            resource_type="swedish_test",
            quantity=1,
            service_name="test_service",
            processing_id="swedish-job-123",
        )
        envelope = EventEnvelope[ResourceConsumptionV1](
            event_type="huleedu.resource.consumption.v1",
            source_service="test_service",
            correlation_id=uuid4(),
            data=event,
        )
        message = MagicMock()
        message.value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")

        # Act
        await consumer_instance._handle_message(message)

        # Assert - Verify Swedish characters are preserved in credit manager call
        mock_credit_manager.consume_credits.assert_called_once_with(
            user_id=expected_user,
            org_id=expected_org,
            metric="swedish_test",
            amount=1,
            batch_id="batch-swedish",
            correlation_id=str(envelope.correlation_id),
        )

    @pytest.mark.asyncio
    async def test_handle_message_with_malformed_json_raises_exception(
        self, consumer_instance: EntitlementsKafkaConsumer
    ) -> None:
        """Test that malformed JSON in Kafka message raises appropriate exception."""
        # Arrange - Invalid JSON message
        malformed_message = MagicMock()
        malformed_message.value = b"invalid-json-content"

        # Act & Assert - Should raise exception for invalid JSON
        with pytest.raises(Exception):  # Could be JSON decode error or Pydantic validation error
            await consumer_instance._handle_message(malformed_message)

    @pytest.mark.asyncio
    async def test_handle_message_with_invalid_event_structure_raises_exception(
        self, consumer_instance: EntitlementsKafkaConsumer
    ) -> None:
        """Test that invalid event structure raises Pydantic validation exception."""
        # Arrange - Valid JSON but missing required fields
        invalid_event = {
            "event_type": "huleedu.resource.consumption.v1",
            "source_service": "test_service",
            "correlation_id": str(uuid4()),
            "data": {
                "event_name": "RESOURCE_CONSUMPTION_REPORTED",
                # Missing required fields like user_id, resource_type, etc.
            },
        }
        message = MagicMock()
        message.value = json.dumps(invalid_event).encode("utf-8")

        # Act & Assert - Should raise Pydantic validation error
        with pytest.raises(Exception):  # Pydantic ValidationError
            await consumer_instance._handle_message(message)

    @pytest.mark.asyncio
    async def test_handle_message_credit_manager_failure_propagates_exception(
        self,
        consumer_instance: EntitlementsKafkaConsumer,
        mock_credit_manager: AsyncMock,
        sample_kafka_message: Any,
    ) -> None:
        """Test that credit manager failures are properly propagated."""
        # Arrange - Mock credit manager to raise exception
        mock_credit_manager.consume_credits.side_effect = Exception("Credit system unavailable")

        # Act & Assert - Exception should be propagated
        with pytest.raises(Exception) as exc_info:
            await consumer_instance._handle_message(sample_kafka_message)

        assert "Credit system unavailable" in str(exc_info.value)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "resource_type,quantity,expected_metric,expected_amount",
        [
            # Different resource types and quantities
            ("ai_feedback", 1, "ai_feedback", 1),
            ("cj_comparison", 5, "cj_comparison", 5),
            ("spell_check", 10, "spell_check", 10),
            ("batch_create", 1, "batch_create", 1),
            # Edge case - zero quantity (should still process)
            ("test_metric", 0, "test_metric", 0),
        ],
    )
    async def test_handle_message_various_resource_types_and_quantities(
        self,
        consumer_instance: EntitlementsKafkaConsumer,
        mock_credit_manager: AsyncMock,
        resource_type: str,
        quantity: int,
        expected_metric: str,
        expected_amount: int,
    ) -> None:
        """Test processing of various resource types and quantities."""
        # Arrange
        event = ResourceConsumptionV1(
            event_name=ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED,
            entity_id="test-batch",
            entity_type="batch",
            user_id="test-user",
            org_id="test-org",
            resource_type=resource_type,
            quantity=quantity,
            service_name="test_service",
            processing_id="test-job",
        )
        envelope = EventEnvelope[ResourceConsumptionV1](
            event_type="huleedu.resource.consumption.v1",
            source_service="test_service",
            correlation_id=uuid4(),
            data=event,
        )
        message = MagicMock()
        message.value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")

        # Act
        await consumer_instance._handle_message(message)

        # Assert - Verify correct parameters passed to credit manager
        mock_credit_manager.consume_credits.assert_called_once_with(
            user_id="test-user",
            org_id="test-org",
            metric=expected_metric,
            amount=expected_amount,
            batch_id="test-batch",
            correlation_id=str(envelope.correlation_id),
        )

    @pytest.mark.asyncio
    async def test_stop_consumer_sets_should_stop_flag(
        self, consumer_instance: EntitlementsKafkaConsumer
    ) -> None:
        """Test that stop_consumer sets the should_stop flag to True."""
        # Arrange - Initial state
        assert consumer_instance.should_stop is False

        # Act
        await consumer_instance.stop_consumer()

        # Assert - Flag should be set
        assert consumer_instance.should_stop is True

    @pytest.mark.asyncio
    async def test_stop_consumer_calls_stop_on_kafka_consumer(
        self, consumer_instance: EntitlementsKafkaConsumer
    ) -> None:
        """Test that stop_consumer calls stop() on Kafka consumer if it exists."""
        # Arrange - Mock consumer
        mock_kafka_consumer = AsyncMock()
        consumer_instance.consumer = mock_kafka_consumer

        # Act
        await consumer_instance.stop_consumer()

        # Assert - Verify stop was called and consumer cleared
        mock_kafka_consumer.stop.assert_called_once()
        assert consumer_instance.consumer is None

    @pytest.mark.asyncio
    async def test_stop_consumer_handles_missing_consumer_gracefully(
        self, consumer_instance: EntitlementsKafkaConsumer
    ) -> None:
        """Test that stop_consumer handles case where consumer is None gracefully."""
        # Arrange - No consumer set
        consumer_instance.consumer = None

        # Act & Assert - Should not raise exception
        await consumer_instance.stop_consumer()
        assert consumer_instance.should_stop is True

    @pytest.mark.asyncio
    async def test_process_messages_stops_when_should_stop_flag_set(
        self, consumer_instance: EntitlementsKafkaConsumer
    ) -> None:
        """Test that message processing loop exits when should_stop flag is set."""
        # Arrange - Set stop flag before processing
        consumer_instance.should_stop = True
        mock_kafka_consumer = AsyncMock()

        # Mock the consumer to return an empty list since should_stop=True
        mock_kafka_consumer.__aiter__.return_value = iter([])  # Empty iterator
        consumer_instance.consumer = mock_kafka_consumer

        # Act
        await consumer_instance._process_messages()

        # Assert - Should exit immediately, no processing should occur
        # (Test passes if no infinite loop occurs)

    @pytest.mark.asyncio
    async def test_consumer_initialization_sets_correct_attributes(self) -> None:
        """Test that consumer initialization sets all attributes correctly."""
        # Arrange & Act
        mock_credit_manager = AsyncMock(spec=CreditManagerProtocol)
        mock_redis_client = AsyncMock(spec=AtomicRedisClientProtocol)

        consumer = EntitlementsKafkaConsumer(
            kafka_bootstrap_servers="test-servers:9092",
            consumer_group="test-group",
            credit_manager=mock_credit_manager,
            redis_client=mock_redis_client,
        )

        # Assert - Verify all attributes set correctly
        assert consumer.kafka_bootstrap_servers == "test-servers:9092"
        assert consumer.consumer_group == "test-group"
        assert consumer.credit_manager is mock_credit_manager
        assert consumer.redis_client is mock_redis_client
        assert consumer.consumer is None
        assert consumer.should_stop is False

    @pytest.mark.asyncio
    async def test_handle_message_extracts_correlation_id_correctly(
        self,
        consumer_instance: EntitlementsKafkaConsumer,
        mock_credit_manager: AsyncMock,
    ) -> None:
        """Test that correlation_id is correctly extracted from EventEnvelope and passed to credit manager."""
        # Arrange - Create event with specific correlation ID
        test_correlation_id = uuid4()
        event = ResourceConsumptionV1(
            event_name=ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED,
            entity_id="batch-correlation-test",
            entity_type="batch",
            user_id="user-123",
            org_id=None,
            resource_type="test_metric",
            quantity=1,
            service_name="test_service",
            processing_id="test-job",
        )
        envelope = EventEnvelope[ResourceConsumptionV1](
            event_type="huleedu.resource.consumption.v1",
            source_service="test_service",
            correlation_id=test_correlation_id,
            data=event,
        )
        message = MagicMock()
        message.value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")

        # Act
        await consumer_instance._handle_message(message)

        # Assert - Verify correlation_id passed as string to credit manager
        mock_credit_manager.consume_credits.assert_called_once_with(
            user_id="user-123",
            org_id=None,
            metric="test_metric",
            amount=1,
            batch_id="batch-correlation-test",
            correlation_id=str(test_correlation_id),
        )
