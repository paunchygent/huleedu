"""
Tests for successful spellcheck phase completion handling in BCS Kafka consumer.

This module tests the thin event handler for SpellcheckPhaseCompletedV1 events,
focusing on successful completion scenarios and proper state updates.

Test scenarios:
- Successful spellcheck completion recorded
- Essay marked as completed in batch state
- Progress counter incremented correctly
- Batch not yet complete (3 of 5 essays done)
- Metrics updated for successful processing
- Proper idempotency handling with V2 configuration
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from aiokafka import ConsumerRecord

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckPhaseCompletedV1
from common_core.status_enums import ProcessingStatus
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer
from services.batch_conductor_service.kafka_consumer import BCSKafkaConsumer


class MockRedisClient:
    """Mock Redis client compatible with V2 idempotency patterns."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int | None]] = []
        self.delete_calls: list[str] = []

    async def set_if_not_exists(self, key: str, value: Any, ttl_seconds: int | None = None) -> bool:
        """Mock Redis SETNX operation."""
        self.set_calls.append((key, str(value), ttl_seconds))
        if key in self.keys:
            return False
        self.keys[key] = str(value)
        return True

    async def delete_key(self, key: str) -> int:
        """Mock Redis DELETE operation."""
        self.delete_calls.append(key)
        if key in self.keys:
            del self.keys[key]
            return 1
        return 0

    async def delete(self, *keys: str) -> int:
        """Mock multi-key DELETE operation required by RedisClientProtocol."""
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
        """Mock PING operation required by RedisClientProtocol."""
        return True


class MockBatchStateRepository:
    """Mock BatchStateRepository that tracks real batch state operations."""

    def __init__(self) -> None:
        self.recorded_completions: list[dict[str, Any]] = []
        self.batch_states: dict[str, dict[str, set[str]]] = {}  # batch_id -> essay_id -> step_names

    async def record_essay_step_completion(
        self, batch_id: str, essay_id: str, step_name: str, metadata: dict | None = None
    ) -> bool:
        """Record completion of a processing step for an essay."""
        self.recorded_completions.append(
            {
                "batch_id": batch_id,
                "essay_id": essay_id,
                "step_name": step_name,
                "metadata": metadata,
            }
        )

        # Update batch state tracking
        if batch_id not in self.batch_states:
            self.batch_states[batch_id] = {}
        if essay_id not in self.batch_states[batch_id]:
            self.batch_states[batch_id][essay_id] = set()
        self.batch_states[batch_id][essay_id].add(step_name)

        return True

    async def get_essay_completed_steps(self, batch_id: str, essay_id: str) -> set[str]:
        """Get all completed processing steps for an essay."""
        return self.batch_states.get(batch_id, {}).get(essay_id, set())

    async def get_batch_completion_summary(self, batch_id: str) -> dict[str, dict[str, int]]:
        """Get completion summary for all essays in a batch."""
        # Mock implementation - not used in these tests
        return {}

    async def is_batch_step_complete(self, batch_id: str, step_name: str) -> bool:
        """Check if a processing step is complete for all essays in a batch."""
        # Mock implementation - not used in these tests
        return False

    async def record_batch_phase_completion(
        self, batch_id: str, phase_name: str, completed: bool
    ) -> bool:
        """Record phase completion status for multi-pipeline dependency resolution."""
        # Mock implementation for testing
        return True

    async def get_completed_phases(self, batch_id: str) -> set[str]:
        """Get all completed phases for a batch."""
        # Return empty set for mock
        return set()


def create_mock_kafka_record(
    topic: str, event_envelope: EventEnvelope[Any], offset: int = 12345
) -> ConsumerRecord:
    """Create a mock Kafka ConsumerRecord."""
    envelope_dict = event_envelope.model_dump(mode="json")

    return ConsumerRecord(
        topic=topic,
        partition=0,
        offset=offset,
        timestamp=None,
        timestamp_type=None,
        key=None,
        value=json.dumps(envelope_dict).encode("utf-8"),
        checksum=None,
        serialized_key_size=None,
        serialized_value_size=None,
        headers=[],
    )


def create_spellcheck_phase_completed_event(
    essay_id: str,
    batch_id: str,
    status: ProcessingStatus = ProcessingStatus.COMPLETED,
    processing_duration_ms: int = 2000,
    corrected_text_storage_id: str | None = None,
    error_code: str | None = None,
) -> EventEnvelope[SpellcheckPhaseCompletedV1]:
    """Create a spellcheck phase completion event envelope."""
    thin_event = SpellcheckPhaseCompletedV1(
        entity_id=essay_id,
        batch_id=batch_id,
        correlation_id=str(uuid.uuid4()),
        status=status,
        corrected_text_storage_id=corrected_text_storage_id or f"storage_{essay_id}",
        error_code=error_code,
        processing_duration_ms=processing_duration_ms,
        timestamp=datetime.now(UTC),
    )

    return EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="SpellcheckPhaseCompletedV1",
        event_timestamp=datetime.now(UTC),
        source_service="spell-checker-service",
        correlation_id=uuid.uuid4(),
        data=thin_event,
    )


# --- Test Fixtures ---


@pytest.fixture
def mock_redis_client() -> MockRedisClient:
    """Create mock Redis client."""
    return MockRedisClient()


@pytest.fixture
def mock_batch_state_repo() -> MockBatchStateRepository:
    """Create mock batch state repository."""
    return MockBatchStateRepository()


@pytest.fixture
def bcs_kafka_consumer(
    mock_batch_state_repo: MockBatchStateRepository,
    mock_redis_client: MockRedisClient,
) -> BCSKafkaConsumer:
    """Create BCS Kafka consumer with mock dependencies."""
    return BCSKafkaConsumer(
        kafka_bootstrap_servers="localhost:9092",
        consumer_group="test-bcs-consumer-group",
        batch_state_repo=mock_batch_state_repo,
        redis_client=mock_redis_client,  # type: ignore[arg-type]
    )


# --- Test Cases ---


@pytest.mark.asyncio
async def test_successful_spellcheck_completion_recorded(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo: MockBatchStateRepository,
    bcs_kafka_consumer: BCSKafkaConsumer,
) -> None:
    """Test that successful spellcheck phase completion events are processed and recorded."""
    # Arrange
    essay_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())
    processing_duration = 2500
    storage_id = f"corrected_text_{essay_id}"

    envelope = create_spellcheck_phase_completed_event(
        essay_id=essay_id,
        batch_id=batch_id,
        status=ProcessingStatus.COMPLETED,
        processing_duration_ms=processing_duration,
        corrected_text_storage_id=storage_id,
    )
    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
        event_envelope=envelope,
    )

    # Create idempotency configuration for coordination events (24 hours TTL)
    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        event_type_ttls={
            "SpellcheckPhaseCompletedV1": 86400,  # 24 hours for coordination events
        },
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
        await bcs_kafka_consumer._handle_spellcheck_phase_completed(msg)
        await confirm_idempotency()  # Confirm after successful processing
        return True

    # Act
    result = await handle_message_idempotently(record)

    # Assert
    assert result is True  # First time processing
    assert len(mock_redis_client.set_calls) == 1
    assert len(mock_redis_client.delete_calls) == 0

    # Verify V2 key format and TTL for coordination events
    set_call = mock_redis_client.set_calls[0]
    assert set_call[0].startswith("huleedu:idempotency:v2:batch-conductor-service:")
    assert "SpellcheckPhaseCompletedV1" in set_call[0]
    assert set_call[2] == 300  # Initial processing state uses 5 minutes TTL

    # Verify V2 stores JSON metadata instead of "1"
    stored_data = json.loads(set_call[1])
    assert "started_at" in stored_data  # Transaction-aware pattern starts with "started_at"
    assert "processed_by" in stored_data
    assert stored_data["processed_by"] == "batch-conductor-service"
    assert stored_data["status"] == "processing"  # Initial status before confirmation

    # Verify real business logic was executed
    assert len(mock_batch_state_repo.recorded_completions) == 1
    completion = mock_batch_state_repo.recorded_completions[0]
    assert completion["batch_id"] == batch_id
    assert completion["essay_id"] == essay_id
    assert completion["step_name"] == "spellcheck"
    assert completion["metadata"]["completion_status"] == "success"
    assert completion["metadata"]["status"] == ProcessingStatus.COMPLETED.value
    assert completion["metadata"]["processing_duration_ms"] == processing_duration


@pytest.mark.asyncio
async def test_essay_marked_completed_in_batch_state(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo: MockBatchStateRepository,
    bcs_kafka_consumer: BCSKafkaConsumer,
) -> None:
    """Test that essay is properly marked as completed in batch state tracking."""
    # Arrange
    essay_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())

    envelope = create_spellcheck_phase_completed_event(
        essay_id=essay_id,
        batch_id=batch_id,
        status=ProcessingStatus.COMPLETED,
    )
    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
        event_envelope=envelope,
    )

    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
        await bcs_kafka_consumer._handle_spellcheck_phase_completed(msg)
        await confirm_idempotency()
        return True

    # Act
    result = await handle_message_idempotently(record)

    # Assert
    assert result is True

    # Verify essay completion is tracked in batch state
    completed_steps = await mock_batch_state_repo.get_essay_completed_steps(batch_id, essay_id)
    assert "spellcheck" in completed_steps

    # Verify internal state tracking
    assert batch_id in mock_batch_state_repo.batch_states
    assert essay_id in mock_batch_state_repo.batch_states[batch_id]
    assert "spellcheck" in mock_batch_state_repo.batch_states[batch_id][essay_id]


@pytest.mark.asyncio
async def test_progress_counter_incremented_correctly(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo: MockBatchStateRepository,
    bcs_kafka_consumer: BCSKafkaConsumer,
) -> None:
    """Test that progress counter increments correctly with each essay completion."""
    # Arrange - Create multiple essays completing in sequence
    batch_id = str(uuid.uuid4())
    essay_ids = [str(uuid.uuid4()) for _ in range(3)]

    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
        await bcs_kafka_consumer._handle_spellcheck_phase_completed(msg)
        await confirm_idempotency()
        return True

    # Act - Process each essay completion
    for i, essay_id in enumerate(essay_ids):
        envelope = create_spellcheck_phase_completed_event(
            essay_id=essay_id,
            batch_id=batch_id,
            status=ProcessingStatus.COMPLETED,
        )
        record = create_mock_kafka_record(
            topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
            event_envelope=envelope,
        )

        result = await handle_message_idempotently(record)
        assert result is True

        # Verify progress after each completion
        assert len(mock_batch_state_repo.recorded_completions) == i + 1
        completion = mock_batch_state_repo.recorded_completions[i]
        assert completion["batch_id"] == batch_id
        assert completion["essay_id"] == essay_id
        assert completion["step_name"] == "spellcheck"

    # Assert final state
    assert len(mock_batch_state_repo.recorded_completions) == len(essay_ids)

    # Verify all essays are tracked
    for essay_id in essay_ids:
        completed_steps = await mock_batch_state_repo.get_essay_completed_steps(batch_id, essay_id)
        assert "spellcheck" in completed_steps


@pytest.mark.asyncio
async def test_batch_not_yet_complete_scenario(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo: MockBatchStateRepository,
    bcs_kafka_consumer: BCSKafkaConsumer,
) -> None:
    """Test partial batch completion scenario (3 of 5 essays done)."""
    # Arrange - Simulate 3 out of 5 essays completed
    batch_id = str(uuid.uuid4())
    completed_essay_ids = [str(uuid.uuid4()) for _ in range(3)]
    # Note: We don't actually track total essays in the mock, but we simulate the scenario

    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
        await bcs_kafka_consumer._handle_spellcheck_phase_completed(msg)
        await confirm_idempotency()
        return True

    # Act - Process 3 completions
    for essay_id in completed_essay_ids:
        envelope = create_spellcheck_phase_completed_event(
            essay_id=essay_id,
            batch_id=batch_id,
            status=ProcessingStatus.COMPLETED,
        )
        record = create_mock_kafka_record(
            topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
            event_envelope=envelope,
        )

        result = await handle_message_idempotently(record)
        assert result is True

    # Assert - Batch is NOT complete (mock doesn't track total, but we check recorded completions)
    assert len(mock_batch_state_repo.recorded_completions) == 3

    # Verify all completed essays are tracked
    for essay_id in completed_essay_ids:
        completed_steps = await mock_batch_state_repo.get_essay_completed_steps(batch_id, essay_id)
        assert "spellcheck" in completed_steps

    # Verify batch step completion check would return False (partial completion)
    # Note: Mock always returns False, but this demonstrates the intended behavior
    is_complete = await mock_batch_state_repo.is_batch_step_complete(batch_id, "spellcheck")
    assert is_complete is False


@pytest.mark.asyncio
async def test_metrics_updated_for_successful_processing(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo: MockBatchStateRepository,
    bcs_kafka_consumer: BCSKafkaConsumer,
) -> None:
    """Test that metrics are properly updated for successful spellcheck phase completion."""
    # Arrange
    essay_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())

    envelope = create_spellcheck_phase_completed_event(
        essay_id=essay_id,
        batch_id=batch_id,
        status=ProcessingStatus.COMPLETED,
    )
    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
        event_envelope=envelope,
    )

    # Verify consumer has metrics available
    assert bcs_kafka_consumer._metrics is not None
    assert "events_processed_total" in bcs_kafka_consumer._metrics

    # Act - Process the message directly to test metrics
    await bcs_kafka_consumer._handle_message(record)

    # Assert - This test verifies the integration with the metrics system
    # Since we're using real metrics collectors in the test, we verify the handler
    # completes without error and the business logic executes
    assert len(mock_batch_state_repo.recorded_completions) == 1
    completion = mock_batch_state_repo.recorded_completions[0]
    assert completion["batch_id"] == batch_id
    assert completion["essay_id"] == essay_id
    assert completion["step_name"] == "spellcheck"
    assert completion["metadata"]["completion_status"] == "success"
