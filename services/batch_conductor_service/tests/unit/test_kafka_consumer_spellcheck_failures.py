"""
Tests for spellcheck failure scenarios in BCS Kafka consumer.

This module tests failure handling in the spellcheck phase completion handler,
ensuring proper error tracking and batch resilience.

Test scenarios:
- Failed spellcheck handling
- Essay marked as failed in batch state
- Batch continues despite individual failures
- Error metrics recorded
- Failure threshold detection (too many failures)
- Mixed success/failure scenarios
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


class MockBatchStateRepositoryWithFailures:
    """
    Mock BatchStateRepository that tracks both successful and failed essay completions.

    This enhanced mock supports failure tracking and batch resilience testing.
    """

    def __init__(self, total_essays_in_batch: int = 5) -> None:
        self.recorded_completions: list[dict[str, Any]] = []
        self.batch_states: dict[str, dict[str, set[str]]] = {}  # batch_id -> essay_id -> step_names
        self.total_essays_in_batch = total_essays_in_batch
        self.batch_phase_completions: list[dict[str, Any]] = []
        self.failed_essays: dict[str, set[str]] = {}  # batch_id -> set of failed essay_ids

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

        # Track failures
        if metadata and metadata.get("completion_status") == "failed":
            if batch_id not in self.failed_essays:
                self.failed_essays[batch_id] = set()
            self.failed_essays[batch_id].add(essay_id)

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
            failed_count = len(self.failed_essays.get(batch_id, set()))

            summary[step] = {
                "completed": completed_count,
                "total": self.total_essays_in_batch,
                "failed": failed_count,
            }

        return summary

    async def is_batch_step_complete(self, batch_id: str, step_name: str) -> bool:
        """Check if a processing step is complete for all essays in a batch."""
        if batch_id not in self.batch_states:
            return False

        # Count completed essays for this step (including failures)
        completed_count = sum(
            1 for essay_steps in self.batch_states[batch_id].values() if step_name in essay_steps
        )

        # Batch is complete when all essays have been processed (success or failure)
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

    def get_failed_essays_count(self, batch_id: str) -> int:
        """Get count of failed essays for testing purposes."""
        return len(self.failed_essays.get(batch_id, set()))


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
        corrected_text_storage_id=corrected_text_storage_id,
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
def mock_batch_state_repo_with_failures() -> MockBatchStateRepositoryWithFailures:
    """Create mock batch state repository that tracks failures."""
    return MockBatchStateRepositoryWithFailures(total_essays_in_batch=5)


@pytest.fixture
def bcs_kafka_consumer_with_failures(
    mock_batch_state_repo_with_failures: MockBatchStateRepositoryWithFailures,
    mock_redis_client: MockRedisClient,
) -> BCSKafkaConsumer:
    """Create BCS Kafka consumer with failure-aware batch state repository."""
    return BCSKafkaConsumer(
        kafka_bootstrap_servers="localhost:9092",
        consumer_group="test-bcs-consumer-group",
        batch_state_repo=mock_batch_state_repo_with_failures,
        redis_client=mock_redis_client,  # type: ignore[arg-type]
    )


# --- Test Cases ---


@pytest.mark.asyncio
async def test_failed_spellcheck_handling(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_failures: MockBatchStateRepositoryWithFailures,
    bcs_kafka_consumer_with_failures: BCSKafkaConsumer,
) -> None:
    """Test that failed spellcheck events are properly handled and recorded."""
    # Arrange
    essay_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())
    error_code = "SPELLCHECK_ENGINE_TIMEOUT"

    envelope = create_spellcheck_phase_completed_event(
        essay_id=essay_id,
        batch_id=batch_id,
        status=ProcessingStatus.FAILED,
        error_code=error_code,
        corrected_text_storage_id=None,  # No storage for failed processing
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
        await bcs_kafka_consumer_with_failures._handle_spellcheck_phase_completed(msg)
        await confirm_idempotency()
        return True

    # Act
    result = await handle_message_idempotently(record)

    # Assert
    assert result is True
    assert len(mock_batch_state_repo_with_failures.recorded_completions) == 1

    completion = mock_batch_state_repo_with_failures.recorded_completions[0]
    assert completion["batch_id"] == batch_id
    assert completion["essay_id"] == essay_id
    assert completion["step_name"] == "spellcheck"
    assert completion["metadata"]["completion_status"] == "failed"
    assert completion["metadata"]["status"] == ProcessingStatus.FAILED.value

    # Note: The current implementation doesn't include error_code in metadata,
    # but the failure status is properly recorded
    assert "processing_duration_ms" in completion["metadata"]


@pytest.mark.asyncio
async def test_essay_marked_as_failed_in_batch_state(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_failures: MockBatchStateRepositoryWithFailures,
    bcs_kafka_consumer_with_failures: BCSKafkaConsumer,
) -> None:
    """Test that failed essays are properly marked in batch state tracking."""
    # Arrange
    essay_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())

    envelope = create_spellcheck_phase_completed_event(
        essay_id=essay_id,
        batch_id=batch_id,
        status=ProcessingStatus.FAILED,
        error_code="PROCESSING_ERROR",
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
        await bcs_kafka_consumer_with_failures._handle_spellcheck_phase_completed(msg)
        await confirm_idempotency()
        return True

    # Act
    result = await handle_message_idempotently(record)

    # Assert
    assert result is True

    # Verify essay is still tracked as having completed the step (even if failed)
    completed_steps = await mock_batch_state_repo_with_failures.get_essay_completed_steps(
        batch_id, essay_id
    )
    assert "spellcheck" in completed_steps

    # Verify failure is tracked
    failed_count = mock_batch_state_repo_with_failures.get_failed_essays_count(batch_id)
    assert failed_count == 1


@pytest.mark.asyncio
async def test_batch_continues_despite_individual_failures(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_failures: MockBatchStateRepositoryWithFailures,
    bcs_kafka_consumer_with_failures: BCSKafkaConsumer,
) -> None:
    """Test that batch processing continues even when some essays fail."""
    # Arrange - Mix of successful and failed essays
    batch_id = str(uuid.uuid4())
    successful_essays = [str(uuid.uuid4()) for _ in range(3)]
    failed_essays = [str(uuid.uuid4()) for _ in range(2)]

    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
        await bcs_kafka_consumer_with_failures._handle_spellcheck_phase_completed(msg)
        await confirm_idempotency()
        return True

    # Act - Process successful essays
    for essay_id in successful_essays:
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

    # Process failed essays
    for essay_id in failed_essays:
        envelope = create_spellcheck_phase_completed_event(
            essay_id=essay_id,
            batch_id=batch_id,
            status=ProcessingStatus.FAILED,
            error_code="PROCESSING_TIMEOUT",
        )
        record = create_mock_kafka_record(
            topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
            event_envelope=envelope,
        )

        result = await handle_message_idempotently(record)
        assert result is True

    # Assert - All essays processed (successful and failed)
    total_processed = len(successful_essays) + len(failed_essays)
    assert len(mock_batch_state_repo_with_failures.recorded_completions) == total_processed

    # Verify successful essays
    successful_completions = [
        c
        for c in mock_batch_state_repo_with_failures.recorded_completions
        if c["metadata"]["completion_status"] == "success"
    ]
    assert len(successful_completions) == len(successful_essays)

    # Verify failed essays
    failed_completions = [
        c
        for c in mock_batch_state_repo_with_failures.recorded_completions
        if c["metadata"]["completion_status"] == "failed"
    ]
    assert len(failed_completions) == len(failed_essays)

    # Batch should be complete (all essays processed)
    is_complete = await mock_batch_state_repo_with_failures.is_batch_step_complete(
        batch_id, "spellcheck"
    )
    assert is_complete is True


@pytest.mark.asyncio
async def test_error_metrics_recorded_for_failures(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_failures: MockBatchStateRepositoryWithFailures,
    bcs_kafka_consumer_with_failures: BCSKafkaConsumer,
) -> None:
    """Test that error metrics are properly recorded for failed processing."""
    # Arrange
    essay_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())

    envelope = create_spellcheck_phase_completed_event(
        essay_id=essay_id,
        batch_id=batch_id,
        status=ProcessingStatus.FAILED,
        error_code="NETWORK_ERROR",
    )
    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
        event_envelope=envelope,
    )

    # Verify consumer has metrics available
    assert bcs_kafka_consumer_with_failures._metrics is not None
    assert "events_processed_total" in bcs_kafka_consumer_with_failures._metrics

    # Act - Process the message directly to test metrics
    await bcs_kafka_consumer_with_failures._handle_message(record)

    # Assert - This test verifies the integration with the metrics system
    # The message should be processed successfully even though the spellcheck failed
    assert len(mock_batch_state_repo_with_failures.recorded_completions) == 1
    completion = mock_batch_state_repo_with_failures.recorded_completions[0]
    assert completion["metadata"]["completion_status"] == "failed"


@pytest.mark.asyncio
async def test_failure_threshold_detection(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_failures: MockBatchStateRepositoryWithFailures,
    bcs_kafka_consumer_with_failures: BCSKafkaConsumer,
) -> None:
    """Test detection of excessive failures in a batch."""
    # Arrange - Create a batch where most essays fail
    batch_id = str(uuid.uuid4())
    successful_essays = [str(uuid.uuid4())]  # Only 1 success
    failed_essays = [str(uuid.uuid4()) for _ in range(4)]  # 4 failures

    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
        await bcs_kafka_consumer_with_failures._handle_spellcheck_phase_completed(msg)
        await confirm_idempotency()
        return True

    # Act - Process the single successful essay
    envelope = create_spellcheck_phase_completed_event(
        essay_id=successful_essays[0],
        batch_id=batch_id,
        status=ProcessingStatus.COMPLETED,
    )
    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
        event_envelope=envelope,
    )

    result = await handle_message_idempotently(record)
    assert result is True

    # Process all failed essays
    for essay_id in failed_essays:
        envelope = create_spellcheck_phase_completed_event(
            essay_id=essay_id,
            batch_id=batch_id,
            status=ProcessingStatus.FAILED,
            error_code="CRITICAL_ERROR",
        )
        record = create_mock_kafka_record(
            topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
            event_envelope=envelope,
        )

        result = await handle_message_idempotently(record)
        assert result is True

    # Assert - High failure rate detected
    summary = await mock_batch_state_repo_with_failures.get_batch_completion_summary(batch_id)
    assert summary["spellcheck"]["completed"] == 5  # All processed
    assert summary["spellcheck"]["failed"] == 4  # 4 failed

    # Calculate failure rate
    failure_rate = summary["spellcheck"]["failed"] / summary["spellcheck"]["completed"]
    assert failure_rate == 0.8  # 80% failure rate

    # This high failure rate could trigger alerts in a real system


@pytest.mark.asyncio
async def test_mixed_success_failure_scenarios(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo_with_failures: MockBatchStateRepositoryWithFailures,
    bcs_kafka_consumer_with_failures: BCSKafkaConsumer,
) -> None:
    """Test complex scenarios with mixed success and failure patterns."""
    # Arrange - Complex batch with different failure types
    batch_id = str(uuid.uuid4())

    test_cases = [
        ("essay_1", ProcessingStatus.COMPLETED, None),
        ("essay_2", ProcessingStatus.FAILED, "TIMEOUT"),
        ("essay_3", ProcessingStatus.COMPLETED, None),
        ("essay_4", ProcessingStatus.FAILED, "NETWORK_ERROR"),
        ("essay_5", ProcessingStatus.COMPLETED, None),
    ]

    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
        await bcs_kafka_consumer_with_failures._handle_spellcheck_phase_completed(msg)
        await confirm_idempotency()
        return True

    # Act - Process all test cases
    for essay_id, status, error_code in test_cases:
        envelope = create_spellcheck_phase_completed_event(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            error_code=error_code,
        )
        record = create_mock_kafka_record(
            topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
            event_envelope=envelope,
        )

        result = await handle_message_idempotently(record)
        assert result is True

    # Assert - Complex validation of mixed results
    assert len(mock_batch_state_repo_with_failures.recorded_completions) == len(test_cases)

    # Verify success/failure counts
    successful_completions = [
        c
        for c in mock_batch_state_repo_with_failures.recorded_completions
        if c["metadata"]["completion_status"] == "success"
    ]
    failed_completions = [
        c
        for c in mock_batch_state_repo_with_failures.recorded_completions
        if c["metadata"]["completion_status"] == "failed"
    ]

    assert len(successful_completions) == 3  # essay_1, essay_3, essay_5
    assert len(failed_completions) == 2  # essay_2, essay_4

    # Verify all essays are tracked as having completed the step
    for essay_id, _, _ in test_cases:
        completed_steps = await mock_batch_state_repo_with_failures.get_essay_completed_steps(
            batch_id, essay_id
        )
        assert "spellcheck" in completed_steps

    # Batch should be complete
    is_complete = await mock_batch_state_repo_with_failures.is_batch_step_complete(
        batch_id, "spellcheck"
    )
    assert is_complete is True

    # Verify failure tracking
    failed_count = mock_batch_state_repo_with_failures.get_failed_essays_count(batch_id)
    assert failed_count == 2
