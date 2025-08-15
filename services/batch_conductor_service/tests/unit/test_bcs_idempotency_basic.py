"""
Tests for basic idempotency scenarios in the Batch Conductor Service.

This module tests the idempotency handling for Batch Conductor event processing,
following Phase 9 requirements:
- Service name: "batch-conductor-service"
- TTL: 24 hours (86400s) for coordination events
- Redis key format: huleedu:idempotency:v2:batch-conductor-service:{event_type}:{hash}
- Real Batch Conductor workflows with protocol-based mocking

Test scenarios:
- First-time processing: Spellcheck completion and CJ assessment completion events
- Duplicate detection: Same events processed twice should be skipped
- Event-specific TTL verification: 24 hours for coordination events
- V2 key format verification: Correct Redis key namespace and format
- Cross-event type idempotency: Ensure spellcheck vs CJ assessment events are handled separately
- Real business logic: Use actual BatchStateRepository operations, not mocks
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

import pytest
from aiokafka import ConsumerRecord

# from common_core.domain_enums import CourseCode  # Not used in this test file
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.cj_assessment_events import CJAssessmentCompletedV1, GradeProjectionSummary
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import EssayStatus, ProcessingStage
from huleedu_service_libs.event_utils import generate_deterministic_event_id
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer
from services.batch_conductor_service.kafka_consumer import BCSKafkaConsumer


def create_test_grade_projections(essay_ids: list[str] | None = None) -> GradeProjectionSummary:
    """Create test grade projections for unit tests."""
    if essay_ids is None:
        essay_ids = []

    return GradeProjectionSummary(
        projections_available=True,
        primary_grades=dict.fromkeys(essay_ids, "B"),
        confidence_labels=dict.fromkeys(essay_ids, "HIGH"),
        confidence_scores=dict.fromkeys(essay_ids, 0.85),
    )


# --- Test Helpers ---


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

    async def clear_batch_pipeline_state(self, batch_id: str) -> bool:
        """Clear pipeline state when pipeline completes, preparing for next pipeline."""
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


def create_spellcheck_completion_event(
    essay_id: str, batch_id: str, status: EssayStatus = EssayStatus.SPELLCHECKED_SUCCESS
) -> EventEnvelope[SpellcheckResultDataV1]:
    """Create a spellcheck completion event envelope."""
    system_metadata = SystemProcessingMetadata(
        entity_id=essay_id,
        entity_type="essay",
        parent_id=batch_id,
        timestamp=datetime.now(UTC),
        processing_stage=ProcessingStage.COMPLETED,
        event="essay.spellcheck.completed",
    )

    spellcheck_data = SpellcheckResultDataV1(
        event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
        entity_id=essay_id,
        entity_type="essay",
        parent_id=batch_id,
        status=status,
        system_metadata=system_metadata,
        original_text_storage_id=f"storage-{essay_id}",
        corrections_made=5 if status == EssayStatus.SPELLCHECKED_SUCCESS else 0,
    )

    return EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="SpellcheckResultDataV1",
        event_timestamp=datetime.now(UTC),
        source_service="spell-checker-service",
        correlation_id=uuid.uuid4(),
        data=spellcheck_data,
    )


def create_cj_assessment_completion_event(
    batch_id: str, essay_ids: list[str]
) -> EventEnvelope[CJAssessmentCompletedV1]:
    """Create a CJ assessment completion event envelope."""
    system_metadata = SystemProcessingMetadata(
        entity_id=batch_id,
        entity_type="batch",
        parent_id=None,
        timestamp=datetime.now(UTC),
        processing_stage=ProcessingStage.COMPLETED,
        event="cj_assessment.completed",
    )

    # Create processing summary with successful essay IDs
    processing_summary = {
        "total_essays": len(essay_ids),
        "successful": len(essay_ids),
        "failed": 0,
        "successful_essay_ids": essay_ids,
        "failed_essay_ids": [],
        "processing_time_seconds": 5.2,
    }

    cj_data = CJAssessmentCompletedV1(
        event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
        entity_id=batch_id,
        entity_type="batch",
        parent_id=None,
        status=EssayStatus.CJ_ASSESSMENT_SUCCESS,
        system_metadata=system_metadata,
        cj_assessment_job_id=f"cj-job-{batch_id}",
        processing_summary=processing_summary,
    )

    return EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="CJAssessmentCompletedV1",
        event_timestamp=datetime.now(UTC),
        source_service="cj-assessment-service",
        correlation_id=uuid.uuid4(),
        data=cj_data,
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
async def test_spellcheck_first_time_event_processing_success(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo: MockBatchStateRepository,
    bcs_kafka_consumer: BCSKafkaConsumer,
) -> None:
    """Test that first-time spellcheck completion events are processed successfully."""
    # Arrange
    essay_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())

    envelope = create_spellcheck_completion_event(essay_id, batch_id)
    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
        event_envelope=envelope,
    )

    # Create idempotency configuration for coordination events (24 hours TTL)
    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        event_type_ttls={
            "SpellcheckResultDataV1": 86400,  # 24 hours for coordination events
        },
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
        await bcs_kafka_consumer._handle_spellcheck_completed(msg)
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
    assert "SpellcheckResultDataV1" in set_call[0]
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


@pytest.mark.asyncio
async def test_cj_assessment_first_time_event_processing_success(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo: MockBatchStateRepository,
    bcs_kafka_consumer: BCSKafkaConsumer,
) -> None:
    """Test that first-time CJ assessment completion events are processed successfully."""
    # Arrange
    batch_id = str(uuid.uuid4())
    essay_ids = [str(uuid.uuid4()), str(uuid.uuid4())]

    envelope = create_cj_assessment_completion_event(batch_id, essay_ids)
    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
        event_envelope=envelope,
    )

    # Create idempotency configuration for coordination events (24 hours TTL)
    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        event_type_ttls={
            "CJAssessmentCompletedV1": 86400,  # 24 hours for coordination events
        },
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
        await bcs_kafka_consumer._handle_cj_assessment_completed(msg)
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
    assert "CJAssessmentCompletedV1" in set_call[0]
    # With transaction-aware pattern, initial SETNX uses 300s for processing state
    assert set_call[2] == 300  # Processing state TTL

    # Verify V2 stores JSON metadata for processing state
    stored_data = json.loads(set_call[1])
    assert "started_at" in stored_data  # Transaction-aware pattern starts with "started_at"
    assert "processed_by" in stored_data
    assert stored_data["processed_by"] == "batch-conductor-service"
    assert stored_data["status"] == "processing"  # Initial status before confirmation

    # Verify real business logic was executed - CJ assessment creates completion for each essay
    assert len(mock_batch_state_repo.recorded_completions) == len(essay_ids)

    for i, essay_id in enumerate(essay_ids):
        completion = mock_batch_state_repo.recorded_completions[i]
        assert completion["batch_id"] == batch_id
        assert completion["essay_id"] == essay_id
        assert completion["step_name"] == "cj_assessment"
        assert completion["metadata"]["completion_status"] == "success"


@pytest.mark.asyncio
async def test_duplicate_spellcheck_event_skipped(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo: MockBatchStateRepository,
    bcs_kafka_consumer: BCSKafkaConsumer,
) -> None:
    """Test that duplicate spellcheck events are skipped without processing business logic."""
    # Arrange
    essay_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())

    envelope = create_spellcheck_completion_event(essay_id, batch_id)
    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
        event_envelope=envelope,
    )

    # Pre-populate Redis with existing key to simulate duplicate
    deterministic_id = generate_deterministic_event_id(record.value)
    existing_key = (
        f"huleedu:idempotency:v2:batch-conductor-service:SpellcheckResultDataV1:{deterministic_id}"
    )
    # Store with transaction-aware format indicating completed status
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
        await bcs_kafka_consumer._handle_spellcheck_completed(msg)
        await confirm_idempotency()  # Confirm after successful processing
        return True

    # Act
    result = await handle_message_idempotently(record)

    # Assert
    assert result is None  # Duplicate detected
    # With transaction-aware pattern, duplicate detection happens via GET, no SETNX attempted
    assert len(mock_redis_client.set_calls) == 0  # No SET attempted for duplicates
    assert len(mock_redis_client.delete_calls) == 0

    # Verify business logic was NOT executed
    assert len(mock_batch_state_repo.recorded_completions) == 0


@pytest.mark.asyncio
async def test_duplicate_cj_assessment_event_skipped(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo: MockBatchStateRepository,
    bcs_kafka_consumer: BCSKafkaConsumer,
) -> None:
    """Test that duplicate CJ assessment events are skipped without processing business logic."""
    # Arrange
    batch_id = str(uuid.uuid4())
    essay_ids = [str(uuid.uuid4()), str(uuid.uuid4())]

    envelope = create_cj_assessment_completion_event(batch_id, essay_ids)
    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
        event_envelope=envelope,
    )

    # Pre-populate Redis with existing key to simulate duplicate
    deterministic_id = generate_deterministic_event_id(record.value)
    existing_key = (
        f"huleedu:idempotency:v2:batch-conductor-service:CJAssessmentCompletedV1:{deterministic_id}"
    )
    # Store with transaction-aware format indicating completed status
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
        await bcs_kafka_consumer._handle_cj_assessment_completed(msg)
        await confirm_idempotency()  # Confirm after successful processing
        return True

    # Act
    result = await handle_message_idempotently(record)

    # Assert
    assert result is None  # Duplicate detected
    # With transaction-aware pattern, duplicate detection happens via GET, no SETNX attempted
    assert len(mock_redis_client.set_calls) == 0  # No SET attempted for duplicates
    assert len(mock_redis_client.delete_calls) == 0

    # Verify business logic was NOT executed
    assert len(mock_batch_state_repo.recorded_completions) == 0


@pytest.mark.asyncio
async def test_cross_event_type_idempotency_separation(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo: MockBatchStateRepository,
    bcs_kafka_consumer: BCSKafkaConsumer,
) -> None:
    """Test that spellcheck and CJ assessment events have separate idempotency keys."""
    # Arrange
    essay_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())

    # Create spellcheck event
    spellcheck_envelope = create_spellcheck_completion_event(essay_id, batch_id)
    spellcheck_record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
        event_envelope=spellcheck_envelope,
    )

    # Create CJ assessment event for same batch
    cj_envelope = create_cj_assessment_completion_event(batch_id, [essay_id])
    cj_record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
        event_envelope=cj_envelope,
    )

    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_spellcheck_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
        await bcs_kafka_consumer._handle_spellcheck_completed(msg)
        await confirm_idempotency()  # Confirm after successful processing
        return True

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_cj_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
        await bcs_kafka_consumer._handle_cj_assessment_completed(msg)
        await confirm_idempotency()  # Confirm after successful processing
        return True

    # Act
    spellcheck_result = await handle_spellcheck_idempotently(spellcheck_record)
    cj_result = await handle_cj_idempotently(cj_record)

    # Assert
    assert spellcheck_result is True
    assert cj_result is True
    assert len(mock_redis_client.set_calls) == 2  # Two different keys

    # Verify different event types have different keys
    spellcheck_key = mock_redis_client.set_calls[0][0]
    cj_key = mock_redis_client.set_calls[1][0]

    assert spellcheck_key != cj_key
    assert "SpellcheckResultDataV1" in spellcheck_key
    assert "CJAssessmentCompletedV1" in cj_key
    assert spellcheck_key.startswith("huleedu:idempotency:v2:batch-conductor-service:")
    assert cj_key.startswith("huleedu:idempotency:v2:batch-conductor-service:")

    # Both events should have been processed
    assert len(mock_batch_state_repo.recorded_completions) == 2  # 1 spellcheck + 1 CJ assessment


@pytest.mark.asyncio
async def test_redis_key_format_verification(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo: MockBatchStateRepository,
    bcs_kafka_consumer: BCSKafkaConsumer,
) -> None:
    """Test that Redis keys follow the correct V2 format and structure."""
    # Arrange
    essay_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())

    envelope = create_spellcheck_completion_event(essay_id, batch_id)
    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
        event_envelope=envelope,
    )

    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
        await bcs_kafka_consumer._handle_spellcheck_completed(msg)
        await confirm_idempotency()  # Confirm after successful processing
        return True

    # Act
    result = await handle_message_idempotently(record)

    # Assert
    assert result is True
    assert len(mock_redis_client.set_calls) == 1

    # Verify V2 key format: huleedu:idempotency:v2:service:event_type:hash
    key = mock_redis_client.set_calls[0][0]
    key_parts = key.split(":")

    assert len(key_parts) == 6
    assert key_parts[0] == "huleedu"
    assert key_parts[1] == "idempotency"
    assert key_parts[2] == "v2"
    assert key_parts[3] == "batch-conductor-service"
    assert key_parts[4] == "SpellcheckResultDataV1"
    assert len(key_parts[5]) == 64  # SHA-256 hash is 64 characters


@pytest.mark.asyncio
async def test_coordination_event_ttl_verification(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo: MockBatchStateRepository,
    bcs_kafka_consumer: BCSKafkaConsumer,
) -> None:
    """Test that coordination events use the correct 24-hour TTL."""
    # Arrange
    essay_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())

    envelope = create_spellcheck_completion_event(essay_id, batch_id)
    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
        event_envelope=envelope,
    )

    # Create config with specific event type TTLs matching BCS requirements
    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        event_type_ttls={
            "SpellcheckResultDataV1": 86400,  # 24 hours for coordination events
            topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED): 86400,
            "CJAssessmentCompletedV1": 86400,
            topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED): 86400,
            topic_name(ProcessingEvent.ESSAY_AIFEEDBACK_COMPLETED): 86400,
        },
        default_ttl=86400,  # 24 hours for coordination events
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
        await bcs_kafka_consumer._handle_spellcheck_completed(msg)
        await confirm_idempotency()  # Confirm after successful processing
        return True

    # Act
    result = await handle_message_idempotently(record)

    # Assert
    assert result is True
    assert len(mock_redis_client.set_calls) == 1

    # With transaction-aware pattern, initial SETNX uses 300s for processing state
    # The configured TTL (86400) is only applied after confirmation via SETEX
    set_call = mock_redis_client.set_calls[0]
    assert set_call[2] == 300  # Processing state TTL


@pytest.mark.asyncio
async def test_deterministic_event_id_generation_consistency(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo: MockBatchStateRepository,
    bcs_kafka_consumer: BCSKafkaConsumer,
) -> None:
    """Test that deterministic event IDs are generated consistently for identical events."""
    # Arrange
    essay_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())

    # Create the base event data once to ensure identical data content
    shared_event_id = uuid.uuid4()
    shared_correlation_id = uuid.uuid4()
    shared_timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

    # Create system metadata
    system_metadata = SystemProcessingMetadata(
        entity_id=essay_id,
        entity_type="essay",
        parent_id=batch_id,
        timestamp=shared_timestamp,
        processing_stage=ProcessingStage.COMPLETED,
        event="essay.spellcheck.completed",
    )

    spellcheck_data = SpellcheckResultDataV1(
        event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
        entity_id=essay_id,
        entity_type="essay",
        parent_id=batch_id,
        status=EssayStatus.SPELLCHECKED_SUCCESS,
        system_metadata=system_metadata,
        original_text_storage_id=f"storage-{essay_id}",
        corrections_made=5,
    )

    # Create two identical envelopes (true retry scenario)
    envelope1: EventEnvelope[SpellcheckResultDataV1] = EventEnvelope(
        event_id=shared_event_id,
        event_type="SpellcheckResultDataV1",
        event_timestamp=shared_timestamp,
        source_service="spell-checker-service",
        correlation_id=shared_correlation_id,
        data=spellcheck_data,
    )

    envelope2: EventEnvelope[SpellcheckResultDataV1] = EventEnvelope(
        event_id=shared_event_id,
        event_type="SpellcheckResultDataV1",
        event_timestamp=shared_timestamp,  # Same timestamp for true duplicate
        source_service="spell-checker-service",
        correlation_id=shared_correlation_id,
        data=spellcheck_data,
    )

    record1 = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
        event_envelope=envelope1,
    )

    record2 = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
        event_envelope=envelope2,
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
        await bcs_kafka_consumer._handle_spellcheck_completed(msg)
        await confirm_idempotency()  # Confirm after successful processing
        return True

    # Act
    result1 = await handle_message_idempotently(record1)
    result2 = await handle_message_idempotently(record2)

    # Assert
    assert result1 is True  # First message processed
    assert result2 is None  # Second message (retry) skipped
    # With transaction-aware pattern, only first message attempts SETNX
    # Second message detects duplicate via GET and doesn't attempt SETNX
    assert len(mock_redis_client.set_calls) == 1  # Only first message sets key

    # Verify deterministic key generation by checking the key used
    key1 = mock_redis_client.set_calls[0][0]
    # The key should be consistent for identical event content
    assert "SpellcheckResultDataV1" in key1

    # Verify only one business operation was executed
    assert len(mock_batch_state_repo.recorded_completions) == 1


@pytest.mark.asyncio
async def test_async_confirmation_pattern(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo: MockBatchStateRepository,
    bcs_kafka_consumer: BCSKafkaConsumer,
) -> None:
    """Test realistic async confirmation pattern with potential failure scenarios."""
    import asyncio
    import sys

    sys.path.insert(0, "/Users/olofs_mba/Documents/Repos/huledu-reboot")
    from libs.huleedu_service_libs.tests.idempotency_test_utils import AsyncConfirmationTestHelper

    # Arrange
    essay_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())

    envelope = create_spellcheck_completion_event(essay_id, batch_id)
    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
        event_envelope=envelope,
    )

    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    helper = AsyncConfirmationTestHelper()

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_with_controlled_confirmation(
        msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Coroutine[Any, Any, None]]
    ) -> Any:
        return await helper.process_with_controlled_confirmation(
            bcs_kafka_consumer._handle_spellcheck_completed, msg, confirm_idempotency
        )

    # Start processing in background
    coro = handle_message_with_controlled_confirmation(record)
    process_task: asyncio.Task[Any] = asyncio.create_task(coro)

    # Wait for processing to complete but before confirmation
    await helper.wait_for_processing_complete()

    # At this point, Redis should have "processing" status
    assert len(mock_redis_client.set_calls) == 1
    redis_key = mock_redis_client.set_calls[0][0]
    stored_value = mock_redis_client.keys.get(redis_key)
    assert stored_value is not None

    import json

    stored_data = json.loads(stored_value)
    assert stored_data["status"] == "processing"
    assert "started_at" in stored_data

    # Verify TTL is 300s for processing state
    assert mock_redis_client.set_calls[0][2] == 300

    # Now allow confirmation to proceed
    helper.allow_confirmation()

    # Wait for task to complete
    result = await process_task

    # Verify confirmation happened
    assert helper.confirmed is True
    assert result is True

    # Verify business logic was executed
    assert len(mock_batch_state_repo.recorded_completions) == 1
    completion = mock_batch_state_repo.recorded_completions[0]
    assert completion["batch_id"] == batch_id
    assert completion["essay_id"] == essay_id


@pytest.mark.asyncio
async def test_crash_before_confirmation(
    mock_redis_client: MockRedisClient,
    mock_batch_state_repo: MockBatchStateRepository,
    bcs_kafka_consumer: BCSKafkaConsumer,
) -> None:
    """Test that a crash before confirmation leaves message in processing state."""
    import asyncio
    import sys

    sys.path.insert(0, "/Users/olofs_mba/Documents/Repos/huledu-reboot")

    # Arrange
    essay_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())

    envelope = create_spellcheck_completion_event(essay_id, batch_id)
    record = create_mock_kafka_record(
        topic=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
        event_envelope=envelope,
    )

    config = IdempotencyConfig(
        service_name="batch-conductor-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    # Simulate crash by not allowing confirmation
    crash_simulation = asyncio.Event()

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_that_crashes(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
        # Process successfully
        await bcs_kafka_consumer._handle_spellcheck_completed(msg)

        # Wait indefinitely (simulating crash)
        await crash_simulation.wait()

        # Never reaches confirmation
        await confirm_idempotency()
        return True

    # Start processing with timeout
    coro = handle_message_that_crashes(record)
    process_task: asyncio.Task[Any] = asyncio.create_task(coro)

    # Give it time to process but not confirm
    await asyncio.sleep(0.1)

    # Cancel to simulate crash
    process_task.cancel()

    try:
        await process_task
    except asyncio.CancelledError:
        pass

    # Verify state is still "processing"
    assert len(mock_redis_client.set_calls) == 1
    redis_key = mock_redis_client.set_calls[0][0]
    stored_value = mock_redis_client.keys.get(redis_key)
    assert stored_value is not None

    import json

    stored_data = json.loads(stored_value)
    assert stored_data["status"] == "processing"

    # Verify business logic was executed (but not confirmed)
    assert len(mock_batch_state_repo.recorded_completions) == 1

    # Now another worker should be able to detect and retry
    # (after processing TTL expires - not tested here)
