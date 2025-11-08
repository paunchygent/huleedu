"""
Idempotency Integration Tests for Batch Orchestrator Service (Basic Scenarios)

Tests the idempotency decorator for basic success and duplicate detection.
Follows boundary mocking pattern - mocks Redis client but uses real handlers.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from aiokafka import ConsumerRecord
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.pipeline_models import PhaseName
from common_core.status_enums import BatchStatus

from libs.huleedu_service_libs.tests.idempotency_test_utils import AsyncConfirmationTestHelper
from services.batch_orchestrator_service.implementations.batch_essays_ready_handler import (
    BatchEssaysReadyHandler,
)
from services.batch_orchestrator_service.implementations.batch_validation_errors_handler import (
    BatchValidationErrorsHandler,
)
from services.batch_orchestrator_service.implementations.client_pipeline_request_handler import (
    ClientPipelineRequestHandler,
)
from services.batch_orchestrator_service.implementations.els_batch_phase_outcome_handler import (
    ELSBatchPhaseOutcomeHandler,
)
from services.batch_orchestrator_service.kafka_consumer import BatchKafkaConsumer
from services.batch_orchestrator_service.tests import make_prompt_ref


class MockRedisClient:
    """Mock Redis client that tracks calls for testing idempotency behavior."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int]] = []
        self.setex_calls: list[tuple[str, int, str]] = []
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

    async def delete(self, *keys: str) -> int:
        """Mock multi-key DELETE operation required by RedisClientProtocol."""
        total_deleted = 0
        for key in keys:
            deleted_count = await self.delete_key(key)
            total_deleted += deleted_count
        return total_deleted

    async def get(self, key: str) -> str | None:
        """Mock GET operation that retrieves values."""
        return self.keys.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        """Mock SETEX operation that sets values with TTL."""
        self.setex_calls.append((key, ttl_seconds, value))
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
        topic = topic_name(ProcessingEvent.BATCH_ESSAYS_READY)
    elif "batch.phase.outcome" in event_type:
        topic = topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME)
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
        "event_type": topic_name(ProcessingEvent.BATCH_ESSAYS_READY),
        "event_timestamp": datetime.now(UTC).isoformat(),
        "source_service": "essay_lifecycle_service",
        "correlation_id": correlation_id,
        "data": {
            "event": "batch.essays.ready",
            "entity_id": batch_id,
            "entity_type": "batch",
            "batch_id": batch_id,
            "ready_essays": [
                {"essay_id": "essay-1", "text_storage_id": "storage-1"},
                {"essay_id": "essay-2", "text_storage_id": "storage-2"},
            ],
            "metadata": {
                "entity_id": batch_id,
                "entity_type": "batch",
                "timestamp": datetime.now(UTC).isoformat(),
                "processing_stage": "pending",
                "event": "batch.essays.ready",
            },
            # Enhanced lean registration fields (required by updated BatchEssaysReady model)
            "course_code": CourseCode.ENG5.value,
            "course_language": "en",
            "student_prompt_ref": make_prompt_ref(
                "prompt-idempotency-basic"
            ).model_dump(mode="json"),
            "class_type": "GUEST",
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
        "event_type": topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME),
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
def mock_handlers() -> tuple[
    BatchEssaysReadyHandler, BatchValidationErrorsHandler, ELSBatchPhaseOutcomeHandler
]:
    """Create real handler instances with mocked dependencies (boundary mocking)."""
    mock_event_publisher = AsyncMock()
    mock_batch_repo = AsyncMock()
    mock_phase_coordinator = AsyncMock()
    # Mock setup for repository essay storage operations
    mock_batch_repo.store_batch_essays.return_value = True
    mock_batch_repo.get_batch_by_id.return_value = {
        "id": "test-batch-id",
        "status": BatchStatus.STUDENT_VALIDATION_COMPLETED.value,
    }
    mock_batch_repo.update_batch_status.return_value = True
    batch_essays_ready_handler = BatchEssaysReadyHandler(
        event_publisher=mock_event_publisher,
        batch_repo=mock_batch_repo,
    )
    batch_validation_errors_handler = BatchValidationErrorsHandler(
        event_publisher=mock_event_publisher,
        batch_repo=mock_batch_repo,
    )
    els_phase_outcome_handler = ELSBatchPhaseOutcomeHandler(
        phase_coordinator=mock_phase_coordinator,
    )
    return batch_essays_ready_handler, batch_validation_errors_handler, els_phase_outcome_handler


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
        mock_handlers: tuple[
            BatchEssaysReadyHandler, BatchValidationErrorsHandler, ELSBatchPhaseOutcomeHandler
        ],
        mock_client_pipeline_request_handler: AsyncMock,
    ) -> None:
        """Test that first-time BatchEssaysReady events are processed successfully."""
        from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

        redis_client = MockRedisClient()
        batch_essays_ready_handler, batch_validation_errors_handler, els_phase_outcome_handler = (
            mock_handlers
        )
        kafka_msg = create_mock_kafka_message(sample_batch_essays_ready_event)

        config = IdempotencyConfig(service_name="batch-service", enable_debug_logging=True)

        @idempotent_consumer(redis_client=redis_client, config=config)
        async def handle_message_idempotently(
            msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Coroutine[Any, Any, None]]
        ) -> bool:
            # Mock the Phase 1 handlers
            mock_batch_content_provisioning_completed_handler = AsyncMock()
            mock_student_associations_confirmed_handler = AsyncMock()

            consumer = BatchKafkaConsumer(
                kafka_bootstrap_servers="test:9092",
                consumer_group="test-group",
                batch_essays_ready_handler=batch_essays_ready_handler,
                batch_content_provisioning_completed_handler=mock_batch_content_provisioning_completed_handler,
                batch_validation_errors_handler=batch_validation_errors_handler,
                els_batch_phase_outcome_handler=els_phase_outcome_handler,
                client_pipeline_request_handler=mock_client_pipeline_request_handler,
                student_associations_confirmed_handler=mock_student_associations_confirmed_handler,
                redis_client=redis_client,
            )
            await consumer._handle_message(msg)
            await confirm_idempotency()  # Confirm after successful processing
            return True

        result = await handle_message_idempotently(kafka_msg)
        assert result is True
        assert len(redis_client.set_calls) == 1
        assert len(redis_client.delete_calls) == 0
        set_call = redis_client.set_calls[0]
        assert set_call[0].startswith(
            "huleedu:idempotency:v2:batch-service:huleedu_els_batch_essays_ready_v1:"
        )
        # v2 decorator stores JSON metadata, not just "1"
        import json

        stored_data = json.loads(set_call[1])
        # Transaction-aware v2: initial lock has 'started_at' and 'status': 'processing'
        assert "started_at" in stored_data
        assert "processed_by" in stored_data
        assert stored_data["processed_by"] == "batch-service"
        assert stored_data["status"] == "processing"
        # TTL should be positive
        assert set_call[2] > 0
        # With new architecture, BatchEssaysReadyHandler only stores essays - no pipeline
        # state calls
        batch_repo_mock = cast(AsyncMock, batch_essays_ready_handler.batch_repo)
        batch_repo_mock.store_batch_essays.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_batch_essays_ready_detection_and_skipping(
        self,
        sample_batch_essays_ready_event: dict,
        mock_handlers: tuple[
            BatchEssaysReadyHandler, BatchValidationErrorsHandler, ELSBatchPhaseOutcomeHandler
        ],
        mock_client_pipeline_request_handler: AsyncMock,
    ) -> None:
        """Test that duplicate BatchEssaysReady events are skipped."""
        from huleedu_service_libs.event_utils import generate_deterministic_event_id
        from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

        redis_client = MockRedisClient()
        batch_essays_ready_handler, batch_validation_errors_handler, els_phase_outcome_handler = (
            mock_handlers
        )
        kafka_msg = create_mock_kafka_message(sample_batch_essays_ready_event)
        deterministic_id = generate_deterministic_event_id(kafka_msg.value)

        # Create v2 idempotency key for duplicate detection
        config = IdempotencyConfig(service_name="batch-service", enable_debug_logging=True)
        event_type = sample_batch_essays_ready_event["event_type"]
        v2_key = config.generate_redis_key(event_type, "dummy", deterministic_id)
        # Store with transaction-aware format indicating completed status
        redis_client.keys[v2_key] = json.dumps(
            {"status": "completed", "processed_at": 123456789, "processed_by": "batch-service"}
        )

        @idempotent_consumer(redis_client=redis_client, config=config)
        async def handle_message_idempotently(
            msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Coroutine[Any, Any, None]]
        ) -> bool:
            # Mock the Phase 1 handlers
            mock_batch_content_provisioning_completed_handler = AsyncMock()
            mock_student_associations_confirmed_handler = AsyncMock()

            consumer = BatchKafkaConsumer(
                kafka_bootstrap_servers="test:9092",
                consumer_group="test-group",
                batch_essays_ready_handler=batch_essays_ready_handler,
                batch_content_provisioning_completed_handler=mock_batch_content_provisioning_completed_handler,
                batch_validation_errors_handler=batch_validation_errors_handler,
                els_batch_phase_outcome_handler=els_phase_outcome_handler,
                client_pipeline_request_handler=mock_client_pipeline_request_handler,
                student_associations_confirmed_handler=mock_student_associations_confirmed_handler,
                redis_client=redis_client,
            )
            await consumer._handle_message(msg)
            await confirm_idempotency()  # Confirm after successful processing
            return True

        result = await handle_message_idempotently(kafka_msg)
        assert result is None
        # With transaction-aware pattern, duplicate detection happens via GET, no SETNX attempted
        assert len(redis_client.set_calls) == 0  # No SET attempted for duplicates
        assert len(redis_client.delete_calls) == 0
        # With duplicate detection, handler should not be called at all
        batch_repo_mock = cast(AsyncMock, batch_essays_ready_handler.batch_repo)
        batch_repo_mock.store_batch_essays.assert_not_called()

    @pytest.mark.asyncio
    async def test_first_time_els_phase_outcome_processing_success(
        self,
        sample_els_phase_outcome_event: dict,
        mock_handlers: tuple[
            BatchEssaysReadyHandler, BatchValidationErrorsHandler, ELSBatchPhaseOutcomeHandler
        ],
        mock_client_pipeline_request_handler: AsyncMock,
    ) -> None:
        """Test that first-time ELSBatchPhaseOutcome events are processed successfully."""
        from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

        redis_client = MockRedisClient()
        batch_essays_ready_handler, batch_validation_errors_handler, els_phase_outcome_handler = (
            mock_handlers
        )
        kafka_msg = create_mock_kafka_message(sample_els_phase_outcome_event)

        config = IdempotencyConfig(service_name="batch-service", enable_debug_logging=True)

        @idempotent_consumer(redis_client=redis_client, config=config)
        async def handle_message_idempotently(
            msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Coroutine[Any, Any, None]]
        ) -> bool:
            # Mock the Phase 1 handlers
            mock_batch_content_provisioning_completed_handler = AsyncMock()
            mock_student_associations_confirmed_handler = AsyncMock()

            consumer = BatchKafkaConsumer(
                kafka_bootstrap_servers="test:9092",
                consumer_group="test-group",
                batch_essays_ready_handler=batch_essays_ready_handler,
                batch_content_provisioning_completed_handler=mock_batch_content_provisioning_completed_handler,
                batch_validation_errors_handler=batch_validation_errors_handler,
                els_batch_phase_outcome_handler=els_phase_outcome_handler,
                client_pipeline_request_handler=mock_client_pipeline_request_handler,
                student_associations_confirmed_handler=mock_student_associations_confirmed_handler,
                redis_client=redis_client,
            )
            await consumer._handle_message(msg)
            await confirm_idempotency()  # Confirm after successful processing
            return True

        result = await handle_message_idempotently(kafka_msg)
        assert result is True
        assert len(redis_client.set_calls) == 1
        assert len(redis_client.delete_calls) == 0
        phase_coordinator_mock = cast(AsyncMock, els_phase_outcome_handler.phase_coordinator)
        phase_coordinator_mock.handle_phase_concluded.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_confirmation_pattern(
        self,
        sample_batch_essays_ready_event: dict,
        mock_handlers: tuple[
            BatchEssaysReadyHandler, BatchValidationErrorsHandler, ELSBatchPhaseOutcomeHandler
        ],
        mock_client_pipeline_request_handler: AsyncMock,
    ) -> None:
        """Test that processing and confirmation happen at separate times (async pattern)."""
        from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

        redis_client = MockRedisClient()
        batch_essays_ready_handler, batch_validation_errors_handler, els_phase_outcome_handler = (
            mock_handlers
        )
        kafka_msg = create_mock_kafka_message(sample_batch_essays_ready_event)
        helper = AsyncConfirmationTestHelper()

        config = IdempotencyConfig(service_name="batch-service", enable_debug_logging=True)

        @idempotent_consumer(redis_client=redis_client, config=config)
        async def handle_message_with_controlled_confirmation(
            msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Coroutine[Any, Any, None]]
        ) -> Any:
            # Mock the Phase 1 handlers
            mock_batch_content_provisioning_completed_handler = AsyncMock()
            mock_student_associations_confirmed_handler = AsyncMock()

            consumer = BatchKafkaConsumer(
                kafka_bootstrap_servers="test:9092",
                consumer_group="test-group",
                batch_essays_ready_handler=batch_essays_ready_handler,
                batch_content_provisioning_completed_handler=mock_batch_content_provisioning_completed_handler,
                batch_validation_errors_handler=batch_validation_errors_handler,
                els_batch_phase_outcome_handler=els_phase_outcome_handler,
                client_pipeline_request_handler=mock_client_pipeline_request_handler,
                student_associations_confirmed_handler=mock_student_associations_confirmed_handler,
                redis_client=redis_client,
            )
            return await helper.process_with_controlled_confirmation(
                consumer._handle_message, msg, confirm_idempotency
            )

        # Start processing in background
        coro = handle_message_with_controlled_confirmation(kafka_msg)
        process_task: asyncio.Task[Any] = asyncio.create_task(coro)

        # Wait for processing to complete but before confirmation
        await helper.wait_for_processing_complete()

        # Verify "processing" state with initial TTL
        assert len(redis_client.set_calls) == 1
        set_call = redis_client.set_calls[0]
        stored_data = json.loads(set_call[1])
        assert stored_data["status"] == "processing"
        assert set_call[2] == 300  # Processing TTL

        # Allow confirmation and wait for completion
        helper.allow_confirmation()
        result = await process_task

        # Verify successful completion
        assert result is True
        assert helper.confirmed is True

        # Verify business logic was executed
        batch_repo_mock = cast(AsyncMock, batch_essays_ready_handler.batch_repo)
        batch_repo_mock.store_batch_essays.assert_called_once()

    @pytest.mark.asyncio
    async def test_crash_before_confirmation(
        self,
        sample_batch_essays_ready_event: dict,
        mock_handlers: tuple[
            BatchEssaysReadyHandler, BatchValidationErrorsHandler, ELSBatchPhaseOutcomeHandler
        ],
        mock_client_pipeline_request_handler: AsyncMock,
    ) -> None:
        """Test that a crash before confirmation leaves processing state intact."""
        from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

        redis_client = MockRedisClient()
        batch_essays_ready_handler, batch_validation_errors_handler, els_phase_outcome_handler = (
            mock_handlers
        )
        kafka_msg = create_mock_kafka_message(sample_batch_essays_ready_event)
        helper = AsyncConfirmationTestHelper()

        config = IdempotencyConfig(service_name="batch-service", enable_debug_logging=True)

        @idempotent_consumer(redis_client=redis_client, config=config)
        async def handle_message_with_controlled_confirmation(
            msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Coroutine[Any, Any, None]]
        ) -> Any:
            # Mock the Phase 1 handlers
            mock_batch_content_provisioning_completed_handler = AsyncMock()
            mock_student_associations_confirmed_handler = AsyncMock()

            consumer = BatchKafkaConsumer(
                kafka_bootstrap_servers="test:9092",
                consumer_group="test-group",
                batch_essays_ready_handler=batch_essays_ready_handler,
                batch_content_provisioning_completed_handler=mock_batch_content_provisioning_completed_handler,
                batch_validation_errors_handler=batch_validation_errors_handler,
                els_batch_phase_outcome_handler=els_phase_outcome_handler,
                client_pipeline_request_handler=mock_client_pipeline_request_handler,
                student_associations_confirmed_handler=mock_student_associations_confirmed_handler,
                redis_client=redis_client,
            )
            return await helper.process_with_controlled_confirmation(
                consumer._handle_message, msg, confirm_idempotency
            )

        # Start processing in background
        coro = handle_message_with_controlled_confirmation(kafka_msg)
        process_task: asyncio.Task[Any] = asyncio.create_task(coro)

        # Wait for processing to complete but before confirmation
        await helper.wait_for_processing_complete()

        # Verify "processing" state is set
        assert len(redis_client.set_calls) == 1
        set_call = redis_client.set_calls[0]
        stored_data = json.loads(set_call[1])
        assert stored_data["status"] == "processing"
        assert set_call[2] == 300  # Processing TTL

        # Simulate crash by cancelling the task without allowing confirmation
        process_task.cancel()

        # Verify processing state remains (would be cleaned up by TTL in real Redis)
        final_stored_data = json.loads(redis_client.keys[set_call[0]])
        assert final_stored_data["status"] == "processing"
        assert helper.confirmed is False

        # Verify business logic was executed despite the crash
        batch_repo_mock = cast(AsyncMock, batch_essays_ready_handler.batch_repo)
        batch_repo_mock.store_batch_essays.assert_called_once()
