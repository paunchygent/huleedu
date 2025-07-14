"""
Idempotency Integration Tests for Batch Orchestrator Service (Basic Scenarios)

Tests the idempotency decorator for basic success and duplicate detection.
Follows boundary mocking pattern - mocks Redis client but uses real handlers.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock

import pytest
from aiokafka import ConsumerRecord

from common_core.domain_enums import CourseCode
from common_core.pipeline_models import PhaseName
from services.batch_orchestrator_service.implementations.batch_essays_ready_handler import (
    BatchEssaysReadyHandler,
)
from services.batch_orchestrator_service.implementations.client_pipeline_request_handler import (
    ClientPipelineRequestHandler,
)
from services.batch_orchestrator_service.implementations.els_batch_phase_outcome_handler import (
    ELSBatchPhaseOutcomeHandler,
)
from services.batch_orchestrator_service.kafka_consumer import BatchKafkaConsumer


class MockRedisClient:
    """Mock Redis client that tracks calls for testing idempotency behavior."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int]] = []
        self.delete_calls: list[str] = []
        self.should_fail_set = False

    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        """Mock SETNX operation that tracks calls."""
        self.set_calls.append((key, value, ttl_seconds or 0))
        if self.should_fail_set:
            raise Exception("Redis connection failed")
        if key in self.keys:
            return False
        self.keys[key] = value
        return True

    async def delete_key(self, key: str) -> int:
        """Mock DELETE operation that tracks calls."""
        self.delete_calls.append(key)
        if key in self.keys:
            del self.keys[key]
            return 1
        return 0

    async def get(self, key: str) -> str | None:
        """Mock GET operation that retrieves values."""
        return self.keys.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        """Mock SETEX operation that sets values with TTL."""
        self.keys[key] = value
        return True

    async def ping(self) -> bool:
        """Mock PING operation required by RedisClientProtocol."""
        return True


def create_mock_kafka_message(event_data: dict) -> ConsumerRecord:
    """Create a mock Kafka message from event data."""
    message_value = json.dumps(event_data).encode("utf-8")
    event_type = event_data.get("event_type", "")
    if "batch.essays.ready" in event_type:
        topic = "huleedu.els.batch.essays.ready.v1"
    elif "batch.phase.outcome" in event_type:
        topic = "huleedu.els.batch.phase.outcome.v1"
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
        headers=[],
    )


@pytest.fixture
def sample_batch_essays_ready_event() -> dict:
    """Create sample BatchEssaysReady event for testing with lean registration fields."""
    batch_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "huleedu.batch.essays.ready.v1",
        "event_timestamp": datetime.now(UTC).isoformat(),
        "source_service": "essay_lifecycle_service",
        "correlation_id": correlation_id,
        "data": {
            "event": "batch.essays.ready",
            "batch_id": batch_id,
            "ready_essays": [
                {"essay_id": "essay-1", "text_storage_id": "storage-1"},
                {"essay_id": "essay-2", "text_storage_id": "storage-2"},
            ],
            "batch_entity": {"entity_type": "batch", "entity_id": batch_id},
            "validation_failures": [],
            "metadata": {
                "entity": {"entity_type": "batch", "entity_id": batch_id},
                "timestamp": datetime.now(UTC).isoformat(),
            },
            # Enhanced lean registration fields (required by updated BatchEssaysReady model)
            "course_code": CourseCode.ENG5.value,
            "course_language": "en",
            "essay_instructions": "Test instructions for lean flow idempotency testing.",
            "class_type": "GUEST",
            "teacher_first_name": None,
            "teacher_last_name": None,
        },
    }


@pytest.fixture
def sample_els_phase_outcome_event() -> dict:
    """Create sample ELSBatchPhaseOutcome event for testing."""
    batch_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    from common_core.status_enums import BatchStatus

    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "huleedu.els.batch.phase.outcome.v1",
        "event_timestamp": datetime.now(UTC).isoformat(),
        "source_service": "essay_lifecycle_service",
        "correlation_id": correlation_id,
        "data": {
            "batch_id": batch_id,
            "phase_name": PhaseName.SPELLCHECK.value,
            "phase_status": BatchStatus.COMPLETED_SUCCESSFULLY,
            "processed_essays": [{"essay_id": "essay-1", "text_storage_id": "storage-1-processed"}],
            "failed_essay_ids": [],
        },
    }


@pytest.fixture
def mock_handlers() -> tuple[BatchEssaysReadyHandler, ELSBatchPhaseOutcomeHandler]:
    """Create real handler instances with mocked dependencies (boundary mocking)."""
    mock_event_publisher = AsyncMock()
    mock_batch_repo = AsyncMock()
    mock_phase_coordinator = AsyncMock()
    # Mock setup for repository essay storage operations
    mock_batch_repo.store_batch_essays.return_value = True
    batch_essays_ready_handler = BatchEssaysReadyHandler(
        event_publisher=mock_event_publisher,
        batch_repo=mock_batch_repo,
    )
    els_phase_outcome_handler = ELSBatchPhaseOutcomeHandler(
        phase_coordinator=mock_phase_coordinator,
    )
    return batch_essays_ready_handler, els_phase_outcome_handler


@pytest.fixture
def mock_client_pipeline_request_handler() -> AsyncMock:
    """Create mock ClientPipelineRequestHandler with external dependencies."""
    handler = AsyncMock(spec=ClientPipelineRequestHandler)
    handler.bcs_client = AsyncMock()
    handler.batch_repo = AsyncMock()
    handler.phase_coordinator = AsyncMock()
    return handler


class TestBOSIdempotencyBasic:
    """Basic integration tests for BOS idempotency decorator."""

    @pytest.mark.asyncio
    async def test_first_time_batch_essays_ready_processing_success(
        self,
        sample_batch_essays_ready_event: dict,
        mock_handlers: tuple[BatchEssaysReadyHandler, ELSBatchPhaseOutcomeHandler],
        mock_client_pipeline_request_handler: AsyncMock,
    ) -> None:
        """Test that first-time BatchEssaysReady events are processed successfully."""
        from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer_v2

        redis_client = MockRedisClient()
        batch_essays_ready_handler, els_phase_outcome_handler = mock_handlers
        kafka_msg = create_mock_kafka_message(sample_batch_essays_ready_event)

        config = IdempotencyConfig(service_name="batch-service", enable_debug_logging=True)

        @idempotent_consumer_v2(redis_client=redis_client, config=config)
        async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
            consumer = BatchKafkaConsumer(
                kafka_bootstrap_servers="test:9092",
                consumer_group="test-group",
                batch_essays_ready_handler=batch_essays_ready_handler,
                els_batch_phase_outcome_handler=els_phase_outcome_handler,
                client_pipeline_request_handler=mock_client_pipeline_request_handler,
                redis_client=redis_client,
            )
            await consumer._handle_message(msg)
            return True

        result = await handle_message_idempotently(kafka_msg)
        assert result is True
        assert len(redis_client.set_calls) == 1
        assert len(redis_client.delete_calls) == 0
        set_call = redis_client.set_calls[0]
        assert set_call[0].startswith(
            "huleedu:idempotency:v2:batch-service:huleedu_batch_essays_ready_v1:"
        )
        # v2 decorator stores JSON metadata, not just "1"
        assert "processed_at" in set_call[1]
        assert "processed_by" in set_call[1]
        # TTL should be the default value since event type doesn't match specific config
        # (86400 = 24 hours)
        assert set_call[2] == 86400
        # With new architecture, BatchEssaysReadyHandler only stores essays - no pipeline
        # state calls
        batch_repo_mock = cast(AsyncMock, batch_essays_ready_handler.batch_repo)
        batch_repo_mock.store_batch_essays.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_batch_essays_ready_detection_and_skipping(
        self,
        sample_batch_essays_ready_event: dict,
        mock_handlers: tuple[BatchEssaysReadyHandler, ELSBatchPhaseOutcomeHandler],
        mock_client_pipeline_request_handler: AsyncMock,
    ) -> None:
        """Test that duplicate BatchEssaysReady events are skipped."""
        from huleedu_service_libs.event_utils import generate_deterministic_event_id
        from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer_v2

        redis_client = MockRedisClient()
        batch_essays_ready_handler, els_phase_outcome_handler = mock_handlers
        kafka_msg = create_mock_kafka_message(sample_batch_essays_ready_event)
        deterministic_id = generate_deterministic_event_id(kafka_msg.value)

        # Create v2 idempotency key for duplicate detection
        config = IdempotencyConfig(service_name="batch-service", enable_debug_logging=True)
        event_type = sample_batch_essays_ready_event["event_type"]
        v2_key = config.generate_redis_key(event_type, "dummy", deterministic_id)
        redis_client.keys[v2_key] = '{"processed_at": 123456789, "processed_by": "batch-service"}'

        @idempotent_consumer_v2(redis_client=redis_client, config=config)
        async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
            consumer = BatchKafkaConsumer(
                kafka_bootstrap_servers="test:9092",
                consumer_group="test-group",
                batch_essays_ready_handler=batch_essays_ready_handler,
                els_batch_phase_outcome_handler=els_phase_outcome_handler,
                client_pipeline_request_handler=mock_client_pipeline_request_handler,
                redis_client=redis_client,
            )
            await consumer._handle_message(msg)
            return True

        result = await handle_message_idempotently(kafka_msg)
        assert result is None
        assert len(redis_client.set_calls) == 1
        assert len(redis_client.delete_calls) == 0
        # With duplicate detection, handler should not be called at all
        batch_repo_mock = cast(AsyncMock, batch_essays_ready_handler.batch_repo)
        batch_repo_mock.store_batch_essays.assert_not_called()

    @pytest.mark.asyncio
    async def test_first_time_els_phase_outcome_processing_success(
        self,
        sample_els_phase_outcome_event: dict,
        mock_handlers: tuple[BatchEssaysReadyHandler, ELSBatchPhaseOutcomeHandler],
        mock_client_pipeline_request_handler: AsyncMock,
    ) -> None:
        """Test that first-time ELSBatchPhaseOutcome events are processed successfully."""
        from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer_v2

        redis_client = MockRedisClient()
        batch_essays_ready_handler, els_phase_outcome_handler = mock_handlers
        kafka_msg = create_mock_kafka_message(sample_els_phase_outcome_event)

        config = IdempotencyConfig(service_name="batch-service", enable_debug_logging=True)

        @idempotent_consumer_v2(redis_client=redis_client, config=config)
        async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
            consumer = BatchKafkaConsumer(
                kafka_bootstrap_servers="test:9092",
                consumer_group="test-group",
                batch_essays_ready_handler=batch_essays_ready_handler,
                els_batch_phase_outcome_handler=els_phase_outcome_handler,
                client_pipeline_request_handler=mock_client_pipeline_request_handler,
                redis_client=redis_client,
            )
            await consumer._handle_message(msg)
            return True

        result = await handle_message_idempotently(kafka_msg)
        assert result is True
        assert len(redis_client.set_calls) == 1
        assert len(redis_client.delete_calls) == 0
        phase_coordinator_mock = cast(AsyncMock, els_phase_outcome_handler.phase_coordinator)
        phase_coordinator_mock.handle_phase_concluded.assert_called_once()
