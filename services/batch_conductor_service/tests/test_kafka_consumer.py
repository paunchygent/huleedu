"""
Unit tests for BCS Kafka consumer event processing.

Tests boundary behavior: Kafka message consumption, event deserialization,
and BatchStateRepository integration with proper mocking of external systems only.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock

import pytest

from common_core.enums import EssayStatus
from services.batch_conductor_service.kafka_consumer import BCSKafkaConsumer


@pytest.fixture
def mock_batch_state_repo():
    """Mock BatchStateRepository for boundary testing."""
    mock = AsyncMock()
    mock.record_essay_step_completion.return_value = True
    return mock


@pytest.fixture
def mock_redis_client():
    """Mock RedisClient for boundary testing."""
    mock = AsyncMock()
    mock.set_if_not_exists.return_value = True
    return mock


@pytest.fixture
def kafka_consumer(mock_batch_state_repo, mock_redis_client):
    """Create BCSKafkaConsumer with mocked dependencies."""
    return BCSKafkaConsumer(
        kafka_bootstrap_servers="localhost:9092",
        consumer_group="test-group",
        batch_state_repo=mock_batch_state_repo,
        redis_client=mock_redis_client,
    )


@pytest.fixture
def sample_message_data():
    """Create a sample event message that matches the expected structure."""
    return {
        "event_id": "550e8400-e29b-41d4-a716-446655440000",
        "event_type": "huleedu.essay.spellcheck.completed.v1",
        "event_timestamp": "2024-01-01T00:00:00Z",
        "source_service": "spell-checker-service",
        "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
        "data": {
            "event_name": "essay.spellcheck.completed",
            "entity_ref": {
                "entity_id": "essay-123",
                "entity_type": "essay",
                "parent_id": "batch-456",
            },
            "status": EssayStatus.SPELLCHECKED_SUCCESS.value,
            "system_metadata": {
                "entity": {
                    "entity_id": "essay-123",
                    "entity_type": "essay",
                    "parent_id": "batch-456",
                },
                "processing_stage": "completed",
                "event": "essay.spellcheck.completed",
            },
            "original_text_storage_id": "text-storage-123",
            "corrections_made": 5,
        },
    }


@pytest.mark.asyncio
async def test_spellcheck_completion_processing(
    kafka_consumer, mock_batch_state_repo, sample_message_data
):
    """Test successful processing of spellcheck completion event."""

    # Create mock Kafka message
    mock_msg = Mock()
    mock_msg.value = json.dumps(sample_message_data)
    mock_msg.topic = "huleedu.development.essay.spellcheck"

    # Process the message
    await kafka_consumer._handle_spellcheck_completed(mock_msg)

    # Verify BatchStateRepository was called correctly
    mock_batch_state_repo.record_essay_step_completion.assert_called_once()
    call_args = mock_batch_state_repo.record_essay_step_completion.call_args

    assert call_args[1]["batch_id"] == "batch-456"
    assert call_args[1]["essay_id"] == "essay-123"
    assert call_args[1]["step_name"] == "spellcheck"
    assert call_args[1]["metadata"]["completion_status"] == "success"


@pytest.mark.asyncio
async def test_spellcheck_missing_batch_id(
    kafka_consumer, mock_batch_state_repo, sample_message_data
):
    """Test handling of spellcheck event with missing batch_id."""

    # Remove batch_id from the event
    sample_message_data["data"]["entity_ref"]["parent_id"] = None
    sample_message_data["data"]["system_metadata"]["entity"]["parent_id"] = None

    mock_msg = Mock()
    mock_msg.value = json.dumps(sample_message_data)
    mock_msg.topic = "huleedu.development.essay.spellcheck"

    # Process the message (should handle gracefully)
    await kafka_consumer._handle_spellcheck_completed(mock_msg)

    # Verify BatchStateRepository was NOT called due to missing batch_id
    mock_batch_state_repo.record_essay_step_completion.assert_not_called()


@pytest.mark.asyncio
async def test_consumer_lifecycle(kafka_consumer):
    """Test consumer start/stop lifecycle management."""

    # Test initial state
    assert not await kafka_consumer.is_consuming()

    # Test stop when not consuming (should handle gracefully)
    await kafka_consumer.stop_consuming()


@pytest.mark.asyncio
async def test_unknown_topic_handling(kafka_consumer):
    """Test handling of messages from unknown topics."""

    mock_msg = Mock()
    mock_msg.value = json.dumps({"test": "data"})
    mock_msg.topic = "unknown.topic"

    # Should handle gracefully without raising
    await kafka_consumer._handle_message(mock_msg)
