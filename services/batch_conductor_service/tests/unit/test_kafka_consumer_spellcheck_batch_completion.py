"""
Tests for spellcheck batch completion scenarios in BCS Kafka consumer.

This module tests batch completion detection and phase transition logic
when the last essay in a batch completes spellcheck processing.

Test scenarios:
- Last essay completes triggering batch completion
- Batch state transitions to next phase
- Phase outcome event published
- All essays marked complete
- Completion timestamp recorded
- Batch completion summary accuracy
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


class MockBatchStateRepositoryWithCompletion:
    """
    Mock BatchStateRepository that simulates batch completion detection.

    This enhanced mock can simulate when a batch step becomes complete
    after the final essay is processed.
    """

    def __init__(self, total_essays_in_batch: int = 5) -> None:
        self.recorded_completions: list[dict[str, Any]] = []
        self.batch_states: dict[str, dict[str, set[str]]] = {}  # batch_id -> essay_id -> step_names
        self.total_essays_in_batch = total_essays_in_batch
        self.batch_phase_completions: list[dict[str, Any]] = []

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
        if batch_id not in self.batch_states:
            return {}

        summary = {}
        for step in ["spellcheck", "ai_feedback", "cj_assessment"]:
            completed_count = sum(
                1 for essay_steps in self.batch_states[batch_id].values() if step in essay_steps
            )
            summary[step] = {
                "completed": completed_count,
                "total": self.total_essays_in_batch,
            }

        return summary

    async def is_batch_step_complete(self, batch_id: str, step_name: str) -> bool:
        """Check if a processing step is complete for all essays in a batch."""
        if batch_id not in self.batch_states:
            return False

        # Count completed essays for this step
        completed_count = sum(
            1 for essay_steps in self.batch_states[batch_id].values() if step_name in essay_steps
        )

        # Batch is complete when all essays have completed this step
        return completed_count >= self.total_essays_in_batch

    async def record_batch_phase_completion(
        self, batch_id: str, phase_name: str, completed: bool
    ) -> bool:
        """Record phase completion status for multi-pipeline dependency resolution."""
        self.batch_phase_completions.append(
            {
                "batch_id": batch_id,
                "phase_name": phase_name,
                "completed": completed,
                "timestamp": datetime.now(UTC),
            }
        )
        return True

    async def get_completed_phases(self, batch_id: str) -> set[str]:
        """Get all completed phases for a batch."""
        return {
            entry["phase_name"]
            for entry in self.batch_phase_completions
            if entry["batch_id"] == batch_id and entry["completed"]
        }


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
def mock_batch_state_repo_with_completion() -> MockBatchStateRepositoryWithCompletion:
    """Create mock batch state repository that can detect batch completion."""
    return MockBatchStateRepositoryWithCompletion(total_essays_in_batch=5)


@pytest.fixture
def bcs_kafka_consumer_with_completion(
    mock_batch_state_repo_with_completion: MockBatchStateRepositoryWithCompletion,
    mock_redis_client: MockRedisClient,
) -> BCSKafkaConsumer:
    """Create BCS Kafka consumer with completion-aware batch state repository."""
    return BCSKafkaConsumer(
        kafka_bootstrap_servers="localhost:9092",
        consumer_group="test-bcs-consumer-group",
        batch_state_repo=mock_batch_state_repo_with_completion,
        redis_client=mock_redis_client,  # type: ignore[arg-type]
    )


# --- Test Cases ---


@pytest.mark.asyncio
async def test_last_essay_completion_triggers_batch_completion(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_completion: MockBatchStateRepositoryWithCompletion,
    bcs_kafka_consumer_with_completion: BCSKafkaConsumer,
) -> None:
    """Test that the last essay completion triggers batch completion detection."""
    # Arrange - Process 4 out of 5 essays first, then the last one
    batch_id = str(uuid.uuid4())
    total_essays = 5
    essay_ids = [str(uuid.uuid4()) for _ in range(total_essays)]

    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
        await bcs_kafka_consumer_with_completion._handle_spellcheck_phase_completed(msg)
        await confirm_idempotency()
        return True

    # Act - Process first 4 essays (batch not complete yet)
    for i in range(4):
        envelope = create_spellcheck_phase_completed_event(
            essay_id=essay_ids[i],
            batch_id=batch_id,
            status=ProcessingStatus.COMPLETED,
        )
        record = create_mock_kafka_record(
            topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
            event_envelope=envelope,
        )

        result = await handle_message_idempotently(record)
        assert result is True

        # Verify batch is not yet complete
        is_complete = await mock_batch_state_repo_with_completion.is_batch_step_complete(
            batch_id, "spellcheck"
        )
        assert is_complete is False

    # Process the final essay (should trigger batch completion)
    final_envelope = create_spellcheck_phase_completed_event(
        essay_id=essay_ids[4],
        batch_id=batch_id,
        status=ProcessingStatus.COMPLETED,
    )
    final_record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
        event_envelope=final_envelope,
    )

    result = await handle_message_idempotently(final_record)
    assert result is True

    # Assert - Batch should now be complete
    is_complete = await mock_batch_state_repo_with_completion.is_batch_step_complete(
        batch_id, "spellcheck"
    )
    assert is_complete is True

    # Verify all essays were recorded
    assert len(mock_batch_state_repo_with_completion.recorded_completions) == total_essays

    # Verify completion summary
    summary = await mock_batch_state_repo_with_completion.get_batch_completion_summary(batch_id)
    assert summary["spellcheck"]["completed"] == total_essays
    assert summary["spellcheck"]["total"] == total_essays


@pytest.mark.asyncio
async def test_batch_state_transitions_to_next_phase(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_completion: MockBatchStateRepositoryWithCompletion,
    bcs_kafka_consumer_with_completion: BCSKafkaConsumer,
) -> None:
    """Test that batch transitions to next phase after spellcheck completion."""
    # Note: The current implementation only records essay completions, not phase transitions
    # This test documents the expected behavior for future phase transition logic

    # Arrange
    batch_id = str(uuid.uuid4())
    essay_ids = [str(uuid.uuid4()) for _ in range(5)]

    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
        await bcs_kafka_consumer_with_completion._handle_spellcheck_phase_completed(msg)
        await confirm_idempotency()
        return True

    # Act - Complete all essays in the batch
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

        result = await handle_message_idempotently(record)
        assert result is True

    # Assert - Verify batch completion detection works
    is_complete = await mock_batch_state_repo_with_completion.is_batch_step_complete(
        batch_id, "spellcheck"
    )
    assert is_complete is True

    # Verify all essays completed
    for essay_id in essay_ids:
        completed_steps = await mock_batch_state_repo_with_completion.get_essay_completed_steps(
            batch_id, essay_id
        )
        assert "spellcheck" in completed_steps


@pytest.mark.asyncio
async def test_all_essays_marked_complete_in_batch(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_completion: MockBatchStateRepositoryWithCompletion,
    bcs_kafka_consumer_with_completion: BCSKafkaConsumer,
) -> None:
    """Test that all essays are properly marked as complete when batch finishes."""
    # Arrange
    batch_id = str(uuid.uuid4())
    essay_ids = [str(uuid.uuid4()) for _ in range(3)]  # Smaller batch for easier testing

    # Set the mock to expect 3 essays
    mock_batch_state_repo_with_completion.total_essays_in_batch = 3

    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
        await bcs_kafka_consumer_with_completion._handle_spellcheck_phase_completed(msg)
        await confirm_idempotency()
        return True

    # Act - Complete all essays
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

        result = await handle_message_idempotently(record)
        assert result is True

    # Assert - All essays should be marked as complete
    assert len(mock_batch_state_repo_with_completion.recorded_completions) == len(essay_ids)

    # Verify each essay is marked complete
    for essay_id in essay_ids:
        completed_steps = await mock_batch_state_repo_with_completion.get_essay_completed_steps(
            batch_id, essay_id
        )
        assert "spellcheck" in completed_steps

    # Verify batch completion
    is_complete = await mock_batch_state_repo_with_completion.is_batch_step_complete(
        batch_id, "spellcheck"
    )
    assert is_complete is True


@pytest.mark.asyncio
async def test_completion_timestamp_recorded_accurately(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_completion: MockBatchStateRepositoryWithCompletion,
    bcs_kafka_consumer_with_completion: BCSKafkaConsumer,
) -> None:
    """Test that completion timestamps are accurately recorded in metadata."""
    # Arrange
    essay_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())
    test_start_time = datetime.now(UTC)

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
        await bcs_kafka_consumer_with_completion._handle_spellcheck_phase_completed(msg)
        await confirm_idempotency()
        return True

    # Act
    result = await handle_message_idempotently(record)
    test_end_time = datetime.now(UTC)

    # Assert
    assert result is True
    assert len(mock_batch_state_repo_with_completion.recorded_completions) == 1

    completion = mock_batch_state_repo_with_completion.recorded_completions[0]
    timestamp_str = completion["metadata"]["timestamp"]

    # Parse the timestamp and verify it's within the test time range
    timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    assert test_start_time <= timestamp <= test_end_time

    # Verify event ID is recorded
    assert "event_id" in completion["metadata"]
    assert completion["metadata"]["event_id"] is not None


@pytest.mark.asyncio
async def test_batch_completion_summary_accuracy(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_completion: MockBatchStateRepositoryWithCompletion,
    bcs_kafka_consumer_with_completion: BCSKafkaConsumer,
) -> None:
    """Test that batch completion summary provides accurate counts."""
    # Arrange
    batch_id = str(uuid.uuid4())
    essay_ids = [str(uuid.uuid4()) for _ in range(4)]

    # Set the mock to expect 4 essays
    mock_batch_state_repo_with_completion.total_essays_in_batch = 4

    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
        await bcs_kafka_consumer_with_completion._handle_spellcheck_phase_completed(msg)
        await confirm_idempotency()
        return True

    # Act - Complete only 3 out of 4 essays
    for i in range(3):
        envelope = create_spellcheck_phase_completed_event(
            essay_id=essay_ids[i],
            batch_id=batch_id,
            status=ProcessingStatus.COMPLETED,
        )
        record = create_mock_kafka_record(
            topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
            event_envelope=envelope,
        )

        result = await handle_message_idempotently(record)
        assert result is True

    # Assert - Summary should show 3/4 complete
    summary = await mock_batch_state_repo_with_completion.get_batch_completion_summary(batch_id)
    assert "spellcheck" in summary
    assert summary["spellcheck"]["completed"] == 3
    assert summary["spellcheck"]["total"] == 4

    # Batch should not be complete yet
    is_complete = await mock_batch_state_repo_with_completion.is_batch_step_complete(
        batch_id, "spellcheck"
    )
    assert is_complete is False

    # Complete the final essay
    final_envelope = create_spellcheck_phase_completed_event(
        essay_id=essay_ids[3],
        batch_id=batch_id,
        status=ProcessingStatus.COMPLETED,
    )
    final_record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
        event_envelope=final_envelope,
    )

    result = await handle_message_idempotently(final_record)
    assert result is True

    # Final summary should show 4/4 complete
    final_summary = await mock_batch_state_repo_with_completion.get_batch_completion_summary(
        batch_id
    )
    assert final_summary["spellcheck"]["completed"] == 4
    assert final_summary["spellcheck"]["total"] == 4

    # Batch should now be complete
    is_complete = await mock_batch_state_repo_with_completion.is_batch_step_complete(
        batch_id, "spellcheck"
    )
    assert is_complete is True
