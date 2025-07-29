"""
Real infrastructure integration tests for Essay Lifecycle Service race condition fix.

Tests the scenario where validation failures arrive before batch registration
using real Redis infrastructure via testcontainers.

Converted from facade pattern to modular DI with real infrastructure testing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.error_enums import FileValidationErrorCode
from common_core.events.batch_coordination_events import (
    BatchEssaysReady,
    BatchEssaysRegistered,
)
from common_core.events.file_events import EssayValidationFailedV1
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from common_core.models.error_models import ErrorDetail
from huleedu_service_libs.redis_client import RedisClient
from testcontainers.redis import RedisContainer

from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.implementations.batch_coordination_handler_impl import (
    DefaultBatchCoordinationHandler,
)
from services.essay_lifecycle_service.implementations.batch_essay_tracker_impl import (
    DefaultBatchEssayTracker,
)
from services.essay_lifecycle_service.implementations.batch_lifecycle_publisher import (
    BatchLifecyclePublisher,
)
from services.essay_lifecycle_service.implementations.batch_tracker_persistence import (
    BatchTrackerPersistence,
)
from services.essay_lifecycle_service.implementations.redis_batch_queries import (
    RedisBatchQueries,
)
from services.essay_lifecycle_service.implementations.redis_batch_state import (
    RedisBatchState,
)
from services.essay_lifecycle_service.implementations.redis_failure_tracker import (
    RedisFailureTracker,
)
from services.essay_lifecycle_service.implementations.redis_script_manager import (
    RedisScriptManager,
)
from services.essay_lifecycle_service.implementations.redis_slot_operations import (
    RedisSlotOperations,
)
from services.essay_lifecycle_service.tests.unit.test_utils import create_mock_session


@pytest.mark.integration
class TestPendingValidationFailuresIntegration:
    """Integration tests for race condition fix where validation failures arrive before batch registration."""

    @pytest.fixture
    async def test_infrastructure(self) -> AsyncIterator[dict[str, Any]]:
        """Set up real Redis infrastructure with modular components."""
        # Start Redis container
        redis_container = RedisContainer("redis:7-alpine")

        with redis_container as redis:
            # Connection string
            redis_url = f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}"

            # Initialize Redis client
            redis_client = RedisClient(
                client_id="test-pending-validation-failures", redis_url=redis_url
            )
            await redis_client.start()

            # Create real modular components
            redis_script_manager = RedisScriptManager(redis_client)
            batch_state = RedisBatchState(redis_client, redis_script_manager)
            batch_queries = RedisBatchQueries(redis_client, redis_script_manager)
            failure_tracker = RedisFailureTracker(redis_client, redis_script_manager)
            slot_operations = RedisSlotOperations(redis_client, redis_script_manager)

            yield {
                "redis_client": redis_client,
                "batch_state": batch_state,
                "batch_queries": batch_queries,
                "failure_tracker": failure_tracker,
                "slot_operations": slot_operations,
                "redis_script_manager": redis_script_manager,
            }

            # Cleanup
            await redis_client.stop()

    @pytest.fixture
    def settings(self) -> Settings:
        """Create test settings."""
        return Settings(redis_transaction_retries=3)

    @pytest.fixture
    async def batch_tracker(
        self, test_infrastructure: dict[str, Any], settings: Settings
    ) -> DefaultBatchEssayTracker:
        """Create batch tracker with modular DI components."""
        # Extract modular components from infrastructure
        batch_state = test_infrastructure["batch_state"]
        batch_queries = test_infrastructure["batch_queries"]
        failure_tracker = test_infrastructure["failure_tracker"]
        slot_operations = test_infrastructure["slot_operations"]

        # Mock persistence (we're not testing database interactions)
        from unittest.mock import AsyncMock

        mock_persistence = AsyncMock(spec=BatchTrackerPersistence)
        mock_persistence.get_batch_from_database = AsyncMock(return_value=None)
        mock_persistence.persist_batch_expectation = AsyncMock()

        return DefaultBatchEssayTracker(
            persistence=mock_persistence,
            batch_state=batch_state,
            batch_queries=batch_queries,
            failure_tracker=failure_tracker,
            slot_operations=slot_operations,
        )

    @pytest.fixture
    async def coordination_handler(
        self,
        batch_tracker: DefaultBatchEssayTracker,
        test_infrastructure: dict[str, Any],
        settings: Settings,
    ) -> tuple[DefaultBatchCoordinationHandler, AsyncMock]:
        """Create coordination handler with real Redis infrastructure."""
        from unittest.mock import AsyncMock

        # Extract real Redis client from infrastructure
        test_infrastructure["redis_client"]

        # Mock repository (we're testing coordination logic)
        mock_repository = AsyncMock()
        mock_repository.create_essay_records_batch = AsyncMock()

        # Add mock session factory to repository
        mock_session = create_mock_session()

        def mock_session_factory_instance() -> AsyncMock:
            return mock_session

        mock_repository.get_session_factory = AsyncMock(return_value=mock_session_factory_instance)

        # Mock Kafka bus
        mock_kafka_bus = AsyncMock()
        mock_kafka_bus.publish = AsyncMock()

        # Mock outbox repository
        mock_outbox_repository = AsyncMock()
        mock_outbox_repository.add_event = AsyncMock(return_value=uuid4())

        # Create real event publisher with mocked dependencies
        # Create mock BatchLifecyclePublisher with kafka_bus attribute for test assertions
        event_publisher = AsyncMock(spec=BatchLifecyclePublisher)
        event_publisher.kafka_bus = mock_kafka_bus

        handler = DefaultBatchCoordinationHandler(
            batch_tracker=batch_tracker,
            repository=mock_repository,
            batch_lifecycle_publisher=event_publisher,
            session_factory=mock_session_factory_instance,
        )

        return handler, event_publisher

    async def test_validation_failure_before_batch_registration_completes_batch(
        self,
        batch_tracker: DefaultBatchEssayTracker,
        coordination_handler: tuple[DefaultBatchCoordinationHandler, AsyncMock],
        test_infrastructure: dict[str, Any],
    ) -> None:
        """
        Test the race condition fix:
        1. Validation failure arrives BEFORE batch registration
        2. Batch registration processes pending failure
        3. Batch completes immediately with 0 ready essays and 1 failure
        """
        # Extract Redis client from infrastructure
        redis_client = test_infrastructure["redis_client"]
        # Arrange
        batch_id = f"test-batch-{uuid4()}"
        essay_id = f"essay-{uuid4()}"
        correlation_id = uuid4()

        # Create validation failure event (arrives FIRST)
        validation_failure = EssayValidationFailedV1(
            batch_id=batch_id,
            file_upload_id=f"upload-{uuid4()}",
            original_file_name="essay1.pdf",
            validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
            validation_error_detail=ErrorDetail(
                error_code="EMPTY_CONTENT",
                message="File is empty",
                correlation_id=correlation_id,
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate",
            ),
            file_size_bytes=0,
            raw_file_storage_id=f"raw-{uuid4()}",
            correlation_id=correlation_id,
        )

        # Act 1: Process validation failure BEFORE batch exists
        failure_result = await batch_tracker.handle_validation_failure(validation_failure)

        # Assert 1: No batch ready event yet (batch doesn't exist)
        assert failure_result is None

        # Verify pending failure was stored in Redis
        pending_key = f"batch:{batch_id}:pending_failures"
        pending_failures = await redis_client.lrange(pending_key, 0, -1)
        assert len(pending_failures) == 1

        # Create batch registration event (arrives SECOND)
        batch_registration = BatchEssaysRegistered(
            batch_id=batch_id,
            essay_ids=[essay_id],  # Only 1 essay expected
            expected_essay_count=1,
            user_id="test-user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_type="batch", entity_id=batch_id),
            ),
            course_code=CourseCode.ENG5,
            essay_instructions="Write an essay",
        )

        # Unpack handler and event publisher
        handler, event_publisher = coordination_handler

        # Act 2: Register batch (should process pending failure and complete)
        registration_result = await handler.handle_batch_essays_registered(
            event_data=batch_registration,
            correlation_id=correlation_id,
        )

        # Assert 2: Registration succeeded
        assert registration_result is True

        # Wait a moment for async operations to complete
        import asyncio

        await asyncio.sleep(0.01)

        # Verify pending failures were processed and removed
        pending_failures_after = await redis_client.lrange(pending_key, 0, -1)
        assert len(pending_failures_after) == 0  # Should be cleared

        # Verify batch is marked as completed
        completed_key = f"batch:{batch_id}:completed"
        is_completed = await redis_client.exists(completed_key)
        assert is_completed == 1  # Redis exists returns 1 for True

        # Verify BatchEssaysReady event was published via Kafka (Kafka-first pattern)
        # Access the underlying Kafka bus mock from the event publisher
        kafka_bus = event_publisher.kafka_bus
        kafka_bus.publish.assert_called_once()
        call_args = kafka_bus.publish.call_args
        envelope = call_args.kwargs["envelope"]

        # Extract the event data from the envelope
        # In Kafka-first pattern, the data is the actual object, not serialized
        ready_event = envelope.data

        # Import the type to check
        from common_core.events.batch_coordination_events import BatchEssaysReady

        assert isinstance(ready_event, BatchEssaysReady)  # Event is the actual object
        assert ready_event.batch_id == batch_id
        assert len(ready_event.ready_essays) == 0  # No successful essays
        assert ready_event.validation_failures is not None
        assert len(ready_event.validation_failures) == 1  # One validation failure
        assert (
            ready_event.validation_failures[0].file_upload_id == validation_failure.file_upload_id
        )

        # Verify batch state in Redis - slots should be consumed by failure
        slots_key = f"batch:{batch_id}:available_slots"
        available_slots = await redis_client.scard(slots_key)
        assert available_slots == 0  # All slots consumed by failure

        # Note: validation_failures key is cleaned up after event creation
        # The actual validation failures are verified in the published event above

    async def test_multiple_pending_failures_all_processed_on_registration(
        self,
        batch_tracker: DefaultBatchEssayTracker,
        coordination_handler: tuple[DefaultBatchCoordinationHandler, AsyncMock],
        test_infrastructure: dict[str, Any],
    ) -> None:
        """Test that multiple pending failures are all processed when batch is registered."""
        # Extract Redis client from infrastructure
        redis_client = test_infrastructure["redis_client"]

        # Arrange
        batch_id = f"test-batch-{uuid4()}"
        essay_ids = [f"essay-{i}-{uuid4()}" for i in range(3)]
        correlation_id = uuid4()

        # Create 3 validation failures that arrive BEFORE batch registration
        validation_failures = []
        for i in range(len(essay_ids)):
            failure = EssayValidationFailedV1(
                batch_id=batch_id,
                file_upload_id=f"upload-{i}-{uuid4()}",
                original_file_name=f"essay{i}.pdf",
                validation_error_code=FileValidationErrorCode.TEXT_EXTRACTION_FAILED,
                validation_error_detail=ErrorDetail(
                    error_code="TEXT_EXTRACTION_FAILED",
                    message=f"Failed to extract text from essay {i}",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    service="file_service",
                    operation="validate",
                ),
                file_size_bytes=1000 + i,
                raw_file_storage_id=f"raw-{i}-{uuid4()}",
                correlation_id=correlation_id,
            )
            validation_failures.append(failure)

            # Process each failure before batch exists
            result = await batch_tracker.handle_validation_failure(failure)
            assert result is None  # No completion yet

        # Verify all 3 pending failures are stored
        pending_key = f"batch:{batch_id}:pending_failures"
        pending_failures = await redis_client.lrange(pending_key, 0, -1)
        assert len(pending_failures) == 3

        # Register batch with 3 essay slots
        batch_registration = BatchEssaysRegistered(
            batch_id=batch_id,
            essay_ids=essay_ids,
            expected_essay_count=3,
            user_id="test-user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_type="batch", entity_id=batch_id),
            ),
            course_code=CourseCode.ENG5,
            essay_instructions="Write an essay",
        )

        # Unpack handler and event publisher
        handler, event_publisher = coordination_handler

        # Track published events by wrapping the Kafka bus mock
        published_events = []
        kafka_bus = event_publisher.kafka_bus
        original_publish = kafka_bus.publish

        async def capture_publish(**kwargs: Any) -> None:
            if "envelope" in kwargs:
                published_events.append(kwargs["envelope"].data)
            await original_publish(**kwargs)

        kafka_bus.publish = capture_publish

        # Act: Register batch
        registration_result = await handler.handle_batch_essays_registered(
            event_data=batch_registration,
            correlation_id=correlation_id,
        )

        # Assert
        assert registration_result is True

        # All pending failures should be processed and cleared
        pending_failures_after = await redis_client.lrange(pending_key, 0, -1)
        assert len(pending_failures_after) == 0

        # Batch should be completed immediately
        assert len(published_events) == 1
        ready_event = published_events[0]

        # Import the type to check
        from common_core.events.batch_coordination_events import BatchEssaysReady

        assert isinstance(ready_event, BatchEssaysReady)
        assert ready_event.batch_id == batch_id
        assert len(ready_event.ready_essays) == 0  # All failed
        assert ready_event.validation_failures is not None
        assert len(ready_event.validation_failures) == 3  # All 3 failures recorded

        # Verify all failures are in the validation failures list
        assert ready_event.validation_failures is not None
        failure_ids = {f.file_upload_id for f in ready_event.validation_failures}
        expected_ids = {f.file_upload_id for f in validation_failures}
        assert failure_ids == expected_ids

    async def test_mixed_scenario_pending_and_normal_failures(
        self,
        batch_tracker: DefaultBatchEssayTracker,
        coordination_handler: tuple[DefaultBatchCoordinationHandler, AsyncMock],
        test_infrastructure: dict[str, Any],
    ) -> None:
        """Test scenario with both pending failures (before registration) and normal failures (after)."""
        # Extract Redis client from infrastructure
        redis_client = test_infrastructure["redis_client"]

        # Arrange
        batch_id = f"test-batch-{uuid4()}"
        essay_ids = [f"essay-{i}-{uuid4()}" for i in range(3)]
        correlation_id = uuid4()

        # Create 1 validation failure BEFORE batch registration
        early_failure = EssayValidationFailedV1(
            batch_id=batch_id,
            file_upload_id=f"upload-early-{uuid4()}",
            original_file_name="essay_early.pdf",
            validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
            validation_error_detail=ErrorDetail(
                error_code="EMPTY_CONTENT",
                message="File is empty",
                correlation_id=correlation_id,
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate",
            ),
            file_size_bytes=0,
            raw_file_storage_id=f"raw-early-{uuid4()}",
            correlation_id=correlation_id,
        )

        # Process early failure
        early_result = await batch_tracker.handle_validation_failure(early_failure)
        assert early_result is None

        # Register batch with 3 slots
        batch_registration = BatchEssaysRegistered(
            batch_id=batch_id,
            essay_ids=essay_ids,
            expected_essay_count=3,
            user_id="test-user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_type="batch", entity_id=batch_id),
            ),
            course_code=CourseCode.ENG5,
            essay_instructions="Write an essay",
        )

        # Unpack handler and event publisher
        handler, event_publisher = coordination_handler

        # Register batch (processes 1 pending failure, 2 slots remain)
        await handler.handle_batch_essays_registered(
            event_data=batch_registration,
            correlation_id=correlation_id,
        )

        # Verify batch is NOT complete yet (1 failure, 2 slots remaining)
        completed_key = f"batch:{batch_id}:completed"
        is_completed = await redis_client.exists(completed_key)
        assert is_completed == 0  # Redis exists returns 0 for False

        # Add another failure AFTER registration
        late_failure = EssayValidationFailedV1(
            batch_id=batch_id,
            file_upload_id=f"upload-late-{uuid4()}",
            original_file_name="essay_late.pdf",
            validation_error_code=FileValidationErrorCode.RAW_STORAGE_FAILED,
            validation_error_detail=ErrorDetail(
                error_code="RAW_STORAGE_FAILED",
                message="Failed to store raw file content",
                correlation_id=correlation_id,
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate",
            ),
            file_size_bytes=500,
            raw_file_storage_id=f"raw-late-{uuid4()}",
            correlation_id=correlation_id,
        )

        # Track completion event by wrapping Kafka bus
        completion_event = None
        kafka_bus = event_publisher.kafka_bus
        original_publish = kafka_bus.publish

        async def capture_publish(**kwargs: Any) -> None:
            nonlocal completion_event
            if "envelope" in kwargs:
                completion_event = kwargs["envelope"].data
            await original_publish(**kwargs)

        kafka_bus.publish = capture_publish

        # Process late failure
        late_result = await batch_tracker.handle_validation_failure(late_failure)

        # Batch should still not be complete (2 failures, 1 slot remaining)
        assert late_result is None
        assert completion_event is None

        # Add final failure to complete the batch
        final_failure = EssayValidationFailedV1(
            batch_id=batch_id,
            file_upload_id=f"upload-final-{uuid4()}",
            original_file_name="essay_final.pdf",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_LONG,
            validation_error_detail=ErrorDetail(
                error_code="CONTENT_TOO_LONG",
                message="File content exceeds maximum allowed length",
                correlation_id=correlation_id,
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate",
            ),
            file_size_bytes=10_000_000,
            raw_file_storage_id=f"raw-final-{uuid4()}",
            correlation_id=correlation_id,
        )

        # Process final failure - should complete the batch
        final_result = await batch_tracker.handle_validation_failure(final_failure)

        # Assert batch is now complete
        assert final_result is not None
        ready_event, _ = final_result
        assert isinstance(ready_event, BatchEssaysReady)
        assert len(ready_event.ready_essays) == 0
        assert ready_event.validation_failures is not None
        assert len(ready_event.validation_failures) == 3

        # Verify all failures are accounted for
        failure_names = {f.original_file_name for f in ready_event.validation_failures}
        assert failure_names == {"essay_early.pdf", "essay_late.pdf", "essay_final.pdf"}
