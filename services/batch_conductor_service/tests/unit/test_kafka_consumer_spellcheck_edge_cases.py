"""
Tests for spellcheck edge cases and error conditions in BCS Kafka consumer.

This module tests edge cases, error conditions, and resilience scenarios
for the spellcheck phase completion handler.

Test scenarios:
- Non-existent batch ID
- Duplicate event processing (idempotency)
- Essay not part of batch
- Concurrent updates to same batch
- Repository connection failures
- Invalid event data
- Malformed JSON handling
- Network timeouts and retries
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from aiokafka import ConsumerRecord
from pydantic import ValidationError

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckPhaseCompletedV1
from common_core.status_enums import ProcessingStatus
from huleedu_service_libs.event_utils import generate_deterministic_event_id
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


class MockBatchStateRepositoryWithErrors:
    """
    Mock BatchStateRepository that can simulate various error conditions.
    """

    def __init__(self) -> None:
        self.recorded_completions: list[dict[str, Any]] = []
        self.batch_states: dict[str, dict[str, set[str]]] = {}
        self.simulate_connection_error = False
        self.simulate_timeout = False
        self.known_batch_ids: set[str] = set()

    async def record_essay_step_completion(
        self, batch_id: str, essay_id: str, step_name: str, metadata: dict | None = None
    ) -> bool:
        """Record completion of a processing step for an essay."""
        if self.simulate_connection_error:
            raise ConnectionError("Database connection failed")

        if self.simulate_timeout:
            raise TimeoutError("Database operation timed out")

        # Simulate batch not existing by checking known batch IDs
        if batch_id not in self.known_batch_ids and len(self.known_batch_ids) > 0:
            # Return False to indicate batch not found, but don't raise error
            return False

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
        return {}

    async def is_batch_step_complete(self, batch_id: str, step_name: str) -> bool:
        """Check if a processing step is complete for all essays in a batch."""
        return False

    async def record_batch_phase_completion(
        self, batch_id: str, phase_name: str, completed: bool
    ) -> bool:
        """Record phase completion status for multi-pipeline dependency resolution."""
        return True

    async def get_completed_phases(self, batch_id: str) -> set[str]:
        """Get all completed phases for a batch."""
        return set()

    def add_known_batch(self, batch_id: str) -> None:
        """Add a batch ID to the known batches (for testing batch existence)."""
        self.known_batch_ids.add(batch_id)

    def enable_connection_error(self) -> None:
        """Enable connection error simulation."""
        self.simulate_connection_error = True

    def enable_timeout_error(self) -> None:
        """Enable timeout error simulation."""
        self.simulate_timeout = True

    def reset_error_simulation(self) -> None:
        """Reset error simulation flags."""
        self.simulate_connection_error = False
        self.simulate_timeout = False


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
def mock_batch_state_repo_with_errors() -> MockBatchStateRepositoryWithErrors:
    """Create mock batch state repository that can simulate errors."""
    return MockBatchStateRepositoryWithErrors()


@pytest.fixture
def bcs_kafka_consumer_with_errors(
    mock_batch_state_repo_with_errors: MockBatchStateRepositoryWithErrors,
    mock_redis_client: MockRedisClient,
) -> BCSKafkaConsumer:
    """Create BCS Kafka consumer with error-capable batch state repository."""
    return BCSKafkaConsumer(
        kafka_bootstrap_servers="localhost:9092",
        consumer_group="test-bcs-consumer-group",
        batch_state_repo=mock_batch_state_repo_with_errors,
        redis_client=mock_redis_client,  # type: ignore[arg-type]
    )


# --- Test Cases ---


@pytest.mark.asyncio
async def test_non_existent_batch_id_handling(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_errors: MockBatchStateRepositoryWithErrors,
    bcs_kafka_consumer_with_errors: BCSKafkaConsumer,
) -> None:
    """Test handling of events for non-existent batch IDs."""
    # Arrange
    essay_id = str(uuid.uuid4())
    non_existent_batch_id = str(uuid.uuid4())
    existing_batch_id = str(uuid.uuid4())

    # Set up mock to know about one batch but not the other
    mock_batch_state_repo_with_errors.add_known_batch(existing_batch_id)

    envelope = create_spellcheck_phase_completed_event(
        essay_id=essay_id,
        batch_id=non_existent_batch_id,
        status=ProcessingStatus.COMPLETED,
    )
    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
        event_envelope=envelope,
    )

    # Act - Process the event for non-existent batch
    # This should be handled gracefully (logged but not crash)
    await bcs_kafka_consumer_with_errors._handle_spellcheck_phase_completed(record)

    # Assert - No completions should be recorded for non-existent batch
    assert len(mock_batch_state_repo_with_errors.recorded_completions) == 0

    # The handler should complete without throwing exceptions


@pytest.mark.asyncio
async def test_duplicate_event_processing_idempotency(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_errors: MockBatchStateRepositoryWithErrors,
    bcs_kafka_consumer_with_errors: BCSKafkaConsumer,
) -> None:
    """Test that duplicate spellcheck phase events are handled idempotently."""
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

    # Pre-populate Redis with existing key to simulate duplicate
    deterministic_id = generate_deterministic_event_id(record.value)
    existing_key = (
        f"huleedu:idempotency:v2:batch-conductor-service:"
        f"SpellcheckPhaseCompletedV1:{deterministic_id}"
    )
    mock_redis_client.keys[existing_key] = json.dumps(
        {
            "status": "completed",
            "processed_at": datetime.now(UTC).timestamp(),
            "processed_by": "batch-conductor-service",
        }
    )

    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(
        msg: ConsumerRecord, *, confirm_idempotency
    ) -> bool | None:
        await bcs_kafka_consumer_with_errors._handle_spellcheck_phase_completed(msg)
        await confirm_idempotency()
        return True

    # Act
    result = await handle_message_idempotently(record)

    # Assert
    assert result is None  # Duplicate detected
    assert len(mock_redis_client.set_calls) == 0  # No SET attempted for duplicates

    # Verify business logic was NOT executed for duplicate
    assert len(mock_batch_state_repo_with_errors.recorded_completions) == 0


@pytest.mark.asyncio
async def test_essay_not_part_of_batch_scenario(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_errors: MockBatchStateRepositoryWithErrors,
    bcs_kafka_consumer_with_errors: BCSKafkaConsumer,
) -> None:
    """Test handling when essay ID is not part of the specified batch."""
    # Arrange - This is a data consistency issue that might occur
    essay_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())

    # Simulate known batch but essay not belonging to it
    mock_batch_state_repo_with_errors.add_known_batch(batch_id)

    envelope = create_spellcheck_phase_completed_event(
        essay_id=essay_id,
        batch_id=batch_id,
        status=ProcessingStatus.COMPLETED,
    )
    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
        event_envelope=envelope,
    )

    # Act - Process the event (should be handled gracefully)
    await bcs_kafka_consumer_with_errors._handle_spellcheck_phase_completed(record)

    # Assert - Event should be processed (BCS doesn't validate essay-batch relationships)
    assert len(mock_batch_state_repo_with_errors.recorded_completions) == 1

    completion = mock_batch_state_repo_with_errors.recorded_completions[0]
    assert completion["batch_id"] == batch_id
    assert completion["essay_id"] == essay_id


@pytest.mark.asyncio
async def test_repository_connection_failures(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_errors: MockBatchStateRepositoryWithErrors,
    bcs_kafka_consumer_with_errors: BCSKafkaConsumer,
) -> None:
    """Test handling of database connection failures."""
    # Arrange
    essay_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())

    # Enable connection error simulation
    mock_batch_state_repo_with_errors.enable_connection_error()

    envelope = create_spellcheck_phase_completed_event(
        essay_id=essay_id,
        batch_id=batch_id,
        status=ProcessingStatus.COMPLETED,
    )
    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
        event_envelope=envelope,
    )

    # Act & Assert - Connection error should propagate
    with pytest.raises(ConnectionError, match="Database connection failed"):
        await bcs_kafka_consumer_with_errors._handle_spellcheck_phase_completed(record)

    # No completions should be recorded due to connection failure
    assert len(mock_batch_state_repo_with_errors.recorded_completions) == 0


@pytest.mark.asyncio
async def test_repository_timeout_failures(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_errors: MockBatchStateRepositoryWithErrors,
    bcs_kafka_consumer_with_errors: BCSKafkaConsumer,
) -> None:
    """Test handling of database operation timeouts."""
    # Arrange
    essay_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())

    # Enable timeout error simulation
    mock_batch_state_repo_with_errors.enable_timeout_error()

    envelope = create_spellcheck_phase_completed_event(
        essay_id=essay_id,
        batch_id=batch_id,
        status=ProcessingStatus.COMPLETED,
    )
    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
        event_envelope=envelope,
    )

    # Act & Assert - Timeout error should propagate
    with pytest.raises(TimeoutError, match="Database operation timed out"):
        await bcs_kafka_consumer_with_errors._handle_spellcheck_phase_completed(record)

    # No completions should be recorded due to timeout
    assert len(mock_batch_state_repo_with_errors.recorded_completions) == 0


@pytest.mark.asyncio
async def test_invalid_event_data_handling(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_errors: MockBatchStateRepositoryWithErrors,
    bcs_kafka_consumer_with_errors: BCSKafkaConsumer,
) -> None:
    """Test handling of invalid event data (missing required fields)."""
    # Arrange - Create event with missing entity_id
    batch_id = str(uuid.uuid4())

    # Create malformed thin event (missing entity_id)
    invalid_data = {
        "batch_id": batch_id,
        "correlation_id": str(uuid.uuid4()),
        "status": "completed",
        "processing_duration_ms": 2000,
        "timestamp": datetime.now(UTC).isoformat(),
        # Missing entity_id - this should cause validation error
    }

    envelope_data = {
        "event_id": str(uuid.uuid4()),
        "event_type": "SpellcheckPhaseCompletedV1",
        "event_timestamp": datetime.now(UTC).isoformat(),
        "source_service": "spell-checker-service",
        "correlation_id": str(uuid.uuid4()),
        "data": invalid_data,
    }

    record = ConsumerRecord(
        topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
        partition=0,
        offset=12345,
        timestamp=None,
        timestamp_type=None,
        key=None,
        value=json.dumps(envelope_data).encode("utf-8"),
        checksum=None,
        serialized_key_size=None,
        serialized_value_size=None,
        headers=[],
    )

    # Act & Assert - Should handle validation error gracefully
    with pytest.raises(ValidationError):  # Pydantic validation error
        await bcs_kafka_consumer_with_errors._handle_spellcheck_phase_completed(record)

    # No completions should be recorded due to invalid data
    assert len(mock_batch_state_repo_with_errors.recorded_completions) == 0


@pytest.mark.asyncio
async def test_malformed_json_handling(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_errors: MockBatchStateRepositoryWithErrors,
    bcs_kafka_consumer_with_errors: BCSKafkaConsumer,
) -> None:
    """Test handling of malformed JSON in Kafka messages."""
    # Arrange - Create record with invalid JSON
    malformed_json = b'{"invalid": json, missing quotes and braces'

    record = ConsumerRecord(
        topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
        partition=0,
        offset=12345,
        timestamp=None,
        timestamp_type=None,
        key=None,
        value=malformed_json,
        checksum=None,
        serialized_key_size=None,
        serialized_value_size=None,
        headers=[],
    )

    # Act & Assert - Should handle JSON parsing error
    with pytest.raises(ValidationError):  # Pydantic ValidationError for invalid JSON
        await bcs_kafka_consumer_with_errors._handle_spellcheck_phase_completed(record)

    # No completions should be recorded due to malformed JSON
    assert len(mock_batch_state_repo_with_errors.recorded_completions) == 0


@pytest.mark.asyncio
async def test_missing_entity_id_handling(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_errors: MockBatchStateRepositoryWithErrors,
    bcs_kafka_consumer_with_errors: BCSKafkaConsumer,
) -> None:
    """Test handling when entity_id (essay_id) is None or empty."""
    # Arrange - Create event with empty entity_id
    batch_id = str(uuid.uuid4())

    envelope: EventEnvelope[SpellcheckPhaseCompletedV1] = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="SpellcheckPhaseCompletedV1",
        event_timestamp=datetime.now(UTC),
        source_service="spell-checker-service",
        correlation_id=uuid.uuid4(),
        data=SpellcheckPhaseCompletedV1(
            entity_id="",  # Empty entity_id
            batch_id=batch_id,
            correlation_id=str(uuid.uuid4()),
            status=ProcessingStatus.COMPLETED,
            processing_duration_ms=2000,
            timestamp=datetime.now(UTC),
        ),
    )

    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
        event_envelope=envelope,
    )

    # Act - Process the event with empty entity_id
    await bcs_kafka_consumer_with_errors._handle_spellcheck_phase_completed(record)

    # Assert - Should be handled gracefully (logged as error but not crash)
    # The current implementation checks for empty entity_id and returns early
    assert len(mock_batch_state_repo_with_errors.recorded_completions) == 0


@pytest.mark.asyncio
async def test_missing_batch_id_handling(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_errors: MockBatchStateRepositoryWithErrors,
    bcs_kafka_consumer_with_errors: BCSKafkaConsumer,
) -> None:
    """Test handling when batch_id is None or empty."""
    # Arrange - Create event with empty batch_id
    essay_id = str(uuid.uuid4())

    envelope: EventEnvelope[SpellcheckPhaseCompletedV1] = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="SpellcheckPhaseCompletedV1",
        event_timestamp=datetime.now(UTC),
        source_service="spell-checker-service",
        correlation_id=uuid.uuid4(),
        data=SpellcheckPhaseCompletedV1(
            entity_id=essay_id,
            batch_id="",  # Empty batch_id
            correlation_id=str(uuid.uuid4()),
            status=ProcessingStatus.COMPLETED,
            processing_duration_ms=2000,
            timestamp=datetime.now(UTC),
        ),
    )

    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
        event_envelope=envelope,
    )

    # Act - Process the event with empty batch_id
    await bcs_kafka_consumer_with_errors._handle_spellcheck_phase_completed(record)

    # Assert - Should be handled gracefully (logged as error but not crash)
    # The current implementation checks for empty batch_id and returns early
    assert len(mock_batch_state_repo_with_errors.recorded_completions) == 0


@pytest.mark.asyncio
async def test_concurrent_updates_to_same_batch(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_errors: MockBatchStateRepositoryWithErrors,
    bcs_kafka_consumer_with_errors: BCSKafkaConsumer,
) -> None:
    """Test concurrent processing of multiple essays in the same batch."""
    # Arrange - Multiple events for same batch
    batch_id = str(uuid.uuid4())
    essay_ids = [str(uuid.uuid4()) for _ in range(3)]

    # Create events for concurrent processing
    events = []
    for essay_id in essay_ids:
        envelope = create_spellcheck_phase_completed_event(
            essay_id=essay_id,
            batch_id=batch_id,
            status=ProcessingStatus.COMPLETED,
        )
        record = create_mock_kafka_record(
            topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
            event_envelope=envelope,
        )
        events.append(record)

    # Act - Process all events (simulating concurrent processing)
    for record in events:
        await bcs_kafka_consumer_with_errors._handle_spellcheck_phase_completed(record)

    # Assert - All events should be processed successfully
    assert len(mock_batch_state_repo_with_errors.recorded_completions) == len(essay_ids)

    # Verify all essays are tracked for the same batch
    recorded_batch_ids = {
        c["batch_id"] for c in mock_batch_state_repo_with_errors.recorded_completions
    }
    assert len(recorded_batch_ids) == 1
    assert batch_id in recorded_batch_ids

    # Verify all essays are recorded
    recorded_essay_ids = {
        c["essay_id"] for c in mock_batch_state_repo_with_errors.recorded_completions
    }
    assert recorded_essay_ids == set(essay_ids)
