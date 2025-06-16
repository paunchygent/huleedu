"""
Idempotency Integration Tests for Batch Orchestrator Service

Tests the idempotency decorator integration with real business logic handlers.
Follows boundary mocking pattern - mocks Redis client but uses real handlers.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Tuple
from unittest.mock import AsyncMock

import pytest
from aiokafka import ConsumerRecord
from implementations.batch_essays_ready_handler import BatchEssaysReadyHandler
from implementations.els_batch_phase_outcome_handler import ELSBatchPhaseOutcomeHandler
from kafka_consumer import BatchKafkaConsumer


class MockRedisClient:
    """Mock Redis client that tracks calls for testing idempotency behavior."""

    def __init__(self) -> None:
        self.keys: Dict[str, str] = {}
        self.set_calls: list[Tuple[str, str, int]] = []
        self.delete_calls: list[str] = []
        self.should_fail_set = False

    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        """Mock SETNX operation that tracks calls."""
        # Always track the call, even if it fails
        self.set_calls.append((key, value, ttl_seconds or 0))

        if self.should_fail_set:
            raise Exception("Redis connection failed")

        if key in self.keys:
            return False  # Key already exists (duplicate)

        self.keys[key] = value
        return True  # Key set successfully (first time)

    async def delete_key(self, key: str) -> int:
        """Mock DELETE operation that tracks calls."""
        self.delete_calls.append(key)
        if key in self.keys:
            del self.keys[key]
            return 1
        return 0


def create_mock_kafka_message(event_data: dict) -> ConsumerRecord:
    """Create a mock Kafka message from event data."""
    message_value = json.dumps(event_data).encode('utf-8')

    # Determine correct topic based on event type
    event_type = event_data.get("event_type", "")
    if "batch.essays.ready" in event_type:
        topic = "huleedu.els.batch.essays.ready.v1"
    elif "batch_phase.outcome" in event_type:
        topic = "huleedu.els.batch_phase.outcome.v1"
    else:
        topic = "huleedu.test.unknown"

    return ConsumerRecord(
        topic=topic,
        partition=0,
        offset=123,
        timestamp=int(datetime.now().timestamp() * 1000),
        timestamp_type=1,
        key=None,
        value=message_value,
        checksum=None,
        serialized_key_size=0,
        serialized_value_size=len(message_value),
        headers=[]
    )


@pytest.fixture
def sample_batch_essays_ready_event() -> dict:
    """Create sample BatchEssaysReady event for testing."""
    batch_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())

    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "huleedu.batch.essays.ready.v1",
        "event_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_service": "essay_lifecycle_service",
        "correlation_id": correlation_id,
        "data": {
            "event": "batch.essays.ready",
            "batch_id": batch_id,
            "ready_essays": [
                {
                    "essay_id": "essay-1",
                    "text_storage_id": "storage-1"
                },
                {
                    "essay_id": "essay-2",
                    "text_storage_id": "storage-2"
                }
            ],
            "batch_entity": {
                "entity_type": "batch",
                "entity_id": batch_id
            },
            "validation_failures": [],
            "metadata": {
                "entity": {
                    "entity_type": "batch",
                    "entity_id": batch_id
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }
    }


@pytest.fixture
def sample_els_phase_outcome_event() -> dict:
    """Create sample ELSBatchPhaseOutcome event for testing."""
    batch_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())

    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "huleedu.els.batch_phase.outcome.v1",
        "event_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_service": "essay_lifecycle_service",
        "correlation_id": correlation_id,
        "data": {
            "batch_id": batch_id,
            "phase_name": "spellcheck",
            "phase_status": "COMPLETED_SUCCESSFULLY",
            "processed_essays": [
                {
                    "essay_id": "essay-1",
                    "text_storage_id": "storage-1-processed"
                }
            ],
            "failed_essay_ids": []
        }
    }


@pytest.fixture
def mock_handlers() -> Tuple[BatchEssaysReadyHandler, ELSBatchPhaseOutcomeHandler]:
    """Create real handler instances with mocked dependencies (boundary mocking)."""
    # Mock external dependencies that handlers need
    mock_event_publisher = AsyncMock()
    mock_batch_repo = AsyncMock()
    mock_phase_coordinator = AsyncMock()

    # Create mock spellcheck initiator
    mock_spellcheck_initiator = AsyncMock()

    # Import PhaseName to create proper phase initiators map
    from protocols import PhaseName
    mock_phase_initiators_map: Dict[PhaseName, Any] = {
        PhaseName.SPELLCHECK: mock_spellcheck_initiator
    }

    # Configure successful responses for BatchEssaysReadyHandler
    mock_batch_repo.get_processing_pipeline_state.return_value = {
        "requested_pipelines": ["spellcheck"],
        "spellcheck_status": "PENDING_DEPENDENCIES"
    }
    mock_batch_repo.get_batch_context.return_value = {"some": "context"}

    # Create real handler instances with mocked dependencies
    batch_essays_ready_handler = BatchEssaysReadyHandler(
        event_publisher=mock_event_publisher,
        batch_repo=mock_batch_repo,
        phase_initiators_map=mock_phase_initiators_map
    )

    els_phase_outcome_handler = ELSBatchPhaseOutcomeHandler(
        phase_coordinator=mock_phase_coordinator
    )

    return batch_essays_ready_handler, els_phase_outcome_handler


class TestBOSIdempotencyIntegration:
    """Integration tests for BOS idempotency decorator with real business logic."""

    @pytest.mark.asyncio
    async def test_first_time_batch_essays_ready_processing_success(
        self,
        sample_batch_essays_ready_event: dict,
        mock_handlers: Tuple[
            BatchEssaysReadyHandler,
            ELSBatchPhaseOutcomeHandler,
        ],
    ) -> None:
        """
        Test that first-time BatchEssaysReady events are processed successfully with idempotency.
        """
        from huleedu_service_libs.idempotency import idempotent_consumer

        redis_client = MockRedisClient()
        batch_essays_ready_handler, els_phase_outcome_handler = mock_handlers

        # Create Kafka message
        kafka_msg = create_mock_kafka_message(sample_batch_essays_ready_event)

        # Apply idempotency decorator to real message processor
        @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
        async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
            # Create consumer instance to access _handle_message method
            consumer = BatchKafkaConsumer(
                kafka_bootstrap_servers="test:9092",
                consumer_group="test-group",
                batch_essays_ready_handler=batch_essays_ready_handler,
                els_batch_phase_outcome_handler=els_phase_outcome_handler,
                redis_client=redis_client
            )
            await consumer._handle_message(msg)
            return True  # Success

        # Process message
        result = await handle_message_idempotently(kafka_msg)

        # Assertions
        assert result is True  # Business logic succeeded
        assert len(redis_client.set_calls) == 1  # SETNX was called
        assert len(redis_client.delete_calls) == 0  # No cleanup needed

        # Verify Redis key format and TTL
        set_call = redis_client.set_calls[0]
        assert set_call[0].startswith("huleedu:events:seen:")
        assert set_call[1] == "1"
        assert set_call[2] == 86400  # 24 hours

        # Verify business logic was called
        batch_essays_ready_handler.batch_repo.get_processing_pipeline_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_batch_essays_ready_detection_and_skipping(
        self,
        sample_batch_essays_ready_event: dict,
        mock_handlers: Tuple[
            BatchEssaysReadyHandler,
            ELSBatchPhaseOutcomeHandler,
        ],
    ) -> None:
        """
        Test that duplicate BatchEssaysReady events are skipped without processing business logic.
        """
        from huleedu_service_libs.idempotency import idempotent_consumer

        from common_core.events.utils import generate_deterministic_event_id

        redis_client = MockRedisClient()
        batch_essays_ready_handler, els_phase_outcome_handler = mock_handlers

        # Create Kafka message
        kafka_msg = create_mock_kafka_message(sample_batch_essays_ready_event)

        # Pre-populate Redis with the event key to simulate duplicate
        deterministic_id = generate_deterministic_event_id(kafka_msg.value)
        redis_client.keys[f"huleedu:events:seen:{deterministic_id}"] = "1"

        # Apply idempotency decorator
        @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
        async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
            # Create consumer instance to access _handle_message method
            consumer = BatchKafkaConsumer(
                kafka_bootstrap_servers="test:9092",
                consumer_group="test-group",
                batch_essays_ready_handler=batch_essays_ready_handler,
                els_batch_phase_outcome_handler=els_phase_outcome_handler,
                redis_client=redis_client
            )
            await consumer._handle_message(msg)
            return True  # Success

        # Process message
        result = await handle_message_idempotently(kafka_msg)

        # Assertions
        assert result is None  # Should return None for duplicates
        assert len(redis_client.set_calls) == 1  # SETNX was attempted
        assert len(redis_client.delete_calls) == 0  # No cleanup needed

        # Business logic should NOT have been called
        batch_essays_ready_handler.batch_repo.get_processing_pipeline_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_first_time_els_phase_outcome_processing_success(
        self,
        sample_els_phase_outcome_event: dict,
        mock_handlers: Tuple[
            BatchEssaysReadyHandler,
            ELSBatchPhaseOutcomeHandler,
        ],
    ) -> None:
        """Test that first-time ELSBatchPhaseOutcome events are processed successfully."""
        from huleedu_service_libs.idempotency import idempotent_consumer

        redis_client = MockRedisClient()
        batch_essays_ready_handler, els_phase_outcome_handler = mock_handlers

        # Create Kafka message
        kafka_msg = create_mock_kafka_message(sample_els_phase_outcome_event)

        # Apply idempotency decorator
        @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
        async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
            # Create consumer instance to access _handle_message method
            consumer = BatchKafkaConsumer(
                kafka_bootstrap_servers="test:9092",
                consumer_group="test-group",
                batch_essays_ready_handler=batch_essays_ready_handler,
                els_batch_phase_outcome_handler=els_phase_outcome_handler,
                redis_client=redis_client
            )
            await consumer._handle_message(msg)
            return True  # Success

        # Process message
        result = await handle_message_idempotently(kafka_msg)

        # Assertions
        assert result is True  # Business logic succeeded
        assert len(redis_client.set_calls) == 1  # SETNX was called
        assert len(redis_client.delete_calls) == 0  # No cleanup needed

        # Verify business logic was called
        els_phase_outcome_handler.phase_coordinator.handle_phase_concluded.assert_called_once()

    @pytest.mark.asyncio
    async def test_business_logic_failure_keeps_redis_lock(
        self,
        sample_batch_essays_ready_event: dict,
        mock_handlers: Tuple[
            BatchEssaysReadyHandler,
            ELSBatchPhaseOutcomeHandler,
        ],
    ) -> None:
        """
        Test that business logic failures are treated as infrastructure failures
        and release the lock for retry.
        """
        from huleedu_service_libs.idempotency import idempotent_consumer

        redis_client = MockRedisClient()
        batch_essays_ready_handler, els_phase_outcome_handler = mock_handlers

        # Configure business logic to fail
        batch_essays_ready_handler.batch_repo.get_processing_pipeline_state.side_effect = (
            Exception("Business logic failure")
        )

        # Create Kafka message
        kafka_msg = create_mock_kafka_message(sample_batch_essays_ready_event)

        # Apply idempotency decorator
        @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
        async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
            # Create consumer instance to access _handle_message method
            consumer = BatchKafkaConsumer(
                kafka_bootstrap_servers="test:9092",
                consumer_group="test-group",
                batch_essays_ready_handler=batch_essays_ready_handler,
                els_batch_phase_outcome_handler=els_phase_outcome_handler,
                redis_client=redis_client
            )
            await consumer._handle_message(msg)
            return True  # Success

        # Process message - should raise exception (business logic failure)
        with pytest.raises(Exception, match="Business logic failure"):
            await handle_message_idempotently(kafka_msg)

        # Assertions - BOS treats business logic failures as infrastructure failures
        assert len(redis_client.set_calls) == 1  # SETNX was attempted
        assert len(redis_client.delete_calls) == 1  # Key WAS deleted (allows retry)

    @pytest.mark.asyncio
    async def test_unhandled_exception_releases_redis_lock(
        self, sample_batch_essays_ready_event: dict
    ) -> None:
        """Test that unhandled exceptions release the idempotency lock for retry."""
        from huleedu_service_libs.idempotency import idempotent_consumer

        redis_client = MockRedisClient()

        # Create Kafka message
        kafka_msg = create_mock_kafka_message(sample_batch_essays_ready_event)

        # Apply idempotency decorator to a function that raises an exception
        @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
        async def handle_message_with_exception(msg: ConsumerRecord) -> bool:
            raise RuntimeError("Unhandled exception (e.g., network failure)")

        # Process message - should raise exception
        with pytest.raises(RuntimeError, match="Unhandled exception"):
            await handle_message_with_exception(kafka_msg)

        # Assertions
        assert len(redis_client.set_calls) == 1  # SETNX was attempted
        assert len(redis_client.delete_calls) == 1  # Key was deleted for retry

        # Verify Redis key was deleted
        delete_call = redis_client.delete_calls[0]
        assert delete_call.startswith("huleedu:events:seen:")

    @pytest.mark.asyncio
    async def test_redis_failure_fallback_continues_processing(
        self,
        sample_batch_essays_ready_event: dict,
        mock_handlers: Tuple[
            BatchEssaysReadyHandler,
            ELSBatchPhaseOutcomeHandler,
        ],
    ) -> None:
        """Test that Redis failures fall back to processing without idempotency."""
        from huleedu_service_libs.idempotency import idempotent_consumer

        redis_client = MockRedisClient()
        redis_client.should_fail_set = True  # Force Redis failure
        batch_essays_ready_handler, els_phase_outcome_handler = mock_handlers

        # Create Kafka message
        kafka_msg = create_mock_kafka_message(sample_batch_essays_ready_event)

        # Apply idempotency decorator
        @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
        async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
            # Create consumer instance to access _handle_message method
            consumer = BatchKafkaConsumer(
                kafka_bootstrap_servers="test:9092",
                consumer_group="test-group",
                batch_essays_ready_handler=batch_essays_ready_handler,
                els_batch_phase_outcome_handler=els_phase_outcome_handler,
                redis_client=redis_client
            )
            await consumer._handle_message(msg)
            return True  # Success

        # Process message - should succeed despite Redis failure
        result = await handle_message_idempotently(kafka_msg)

        # Assertions
        assert result is True  # Business logic succeeded
        assert len(redis_client.set_calls) == 1  # SETNX was attempted but failed

        # Verify business logic was executed despite Redis failure
        batch_essays_ready_handler.batch_repo.get_processing_pipeline_state.assert_called_once()
