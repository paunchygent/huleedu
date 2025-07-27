"""
Integration tests for Essay Lifecycle Service race condition fix.

Tests the scenario where validation failures arrive before batch registration.
Uses mocked Redis to test the core logic flow.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

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

from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.implementations.batch_coordination_handler_impl import (
    DefaultBatchCoordinationHandler,
)
from services.essay_lifecycle_service.implementations.batch_essay_tracker_impl import (
    DefaultBatchEssayTracker,
)
from services.essay_lifecycle_service.implementations.batch_tracker_persistence import (
    BatchTrackerPersistence,
)
from services.essay_lifecycle_service.implementations.event_publisher import (
    DefaultEventPublisher,
)
from services.essay_lifecycle_service.implementations.redis_batch_coordinator import (
    RedisBatchCoordinator,
)


@pytest.mark.integration
class TestPendingValidationFailuresIntegration:
    """Integration tests for race condition fix where validation failures arrive before batch registration."""

    @pytest.fixture
    async def redis_client(self) -> AsyncMock:
        """Mock Redis client for testing."""
        from unittest.mock import AsyncMock

        # Create a mock that tracks state across calls
        mock_redis = AsyncMock(spec=RedisClient)

        # Storage for our test data
        mock_redis._data = {
            "lists": {},  # For lrange, rpush
            "sets": {},  # For scard, sadd, spop
            "hashes": {},  # For hgetall, hset
            "strings": {},  # For set, get, exists
        }

        # Mock lrange for pending failures
        async def mock_lrange(key: str, start: int, stop: int) -> list[str]:
            result = mock_redis._data["lists"].get(key, [])
            return list(result)

        mock_redis.lrange = AsyncMock(side_effect=mock_lrange)

        # Mock rpush for pending failures
        async def mock_rpush(key: str, value: str) -> int:
            if key not in mock_redis._data["lists"]:
                mock_redis._data["lists"][key] = []
            mock_redis._data["lists"][key].append(value)
            return len(mock_redis._data["lists"][key])

        mock_redis.rpush = AsyncMock(side_effect=mock_rpush)

        # Mock scard for available slots
        async def mock_scard(key: str) -> int:
            return len(mock_redis._data["sets"].get(key, set()))

        mock_redis.scard = AsyncMock(side_effect=mock_scard)

        # Mock exists for completed check
        async def mock_exists(key: str) -> bool:
            return key in mock_redis._data["strings"]

        mock_redis.exists = AsyncMock(side_effect=mock_exists)

        # Mock hgetall for batch metadata
        async def mock_hgetall(key: str) -> dict[str, str]:
            result = mock_redis._data["hashes"].get(key, {})
            return dict(result)

        mock_redis.hgetall = AsyncMock(side_effect=mock_hgetall)

        # Mock hset for batch metadata
        async def mock_hset(key: str, field: str, value: str) -> int:
            if key not in mock_redis._data["hashes"]:
                mock_redis._data["hashes"][key] = {}
            mock_redis._data["hashes"][key][field] = value
            return 1

        mock_redis.hset = AsyncMock(side_effect=mock_hset)

        # Mock llen for failure count
        async def mock_llen(key: str) -> int:
            return len(mock_redis._data["lists"].get(key, []))

        mock_redis.llen = AsyncMock(side_effect=mock_llen)

        # Mock sadd for adding to sets
        async def mock_sadd(key: str, *values: str) -> int:
            if key not in mock_redis._data["sets"]:
                mock_redis._data["sets"][key] = set()
            added = 0
            for value in values:
                if value not in mock_redis._data["sets"][key]:
                    mock_redis._data["sets"][key].add(value)
                    added += 1
            return added

        mock_redis.sadd = AsyncMock(side_effect=mock_sadd)

        # Mock set for string values
        async def mock_set(key: str, value: str, *args: Any, **kwargs: Any) -> bool:
            mock_redis._data["strings"][key] = value
            return True

        mock_redis.set = AsyncMock(side_effect=mock_set)

        # Mock expire
        mock_redis.expire = AsyncMock(return_value=True)

        # Mock delete
        async def mock_delete(key: str) -> int:
            # Remove from appropriate storage
            deleted = 0
            for storage in mock_redis._data.values():
                if key in storage:
                    del storage[key]
                    deleted = 1
            return deleted

        mock_redis.delete = AsyncMock(side_effect=mock_delete)

        # Mock pipeline operations with actual behavior
        class MockPipeline:
            def __init__(self, redis_mock: Any) -> None:
                self.redis = redis_mock
                self.operations: list[tuple[Any, ...]] = []

            def multi(self) -> MockPipeline:
                return self

            def rpush(self, key: str, value: str) -> MockPipeline:
                self.operations.append(("rpush", key, value))
                return self

            def spop(self, key: str) -> MockPipeline:
                self.operations.append(("spop", key))
                return self

            def delete(self, key: str) -> MockPipeline:
                self.operations.append(("delete", key))
                return self

            def expire(self, key: str, seconds: int) -> MockPipeline:
                self.operations.append(("expire", key, seconds))
                return self

            def hset(self, key: str, field: str, value: str) -> MockPipeline:
                self.operations.append(("hset", key, field, value))
                return self

            def sadd(self, key: str, *values: str) -> MockPipeline:
                for value in values:
                    self.operations.append(("sadd", key, value))
                return self

            def set(self, key: str, value: str, *args: Any, **kwargs: Any) -> MockPipeline:
                self.operations.append(("set", key, value))
                return self

            def setex(self, key: str, seconds: int, value: str) -> MockPipeline:
                self.operations.append(("setex", key, seconds, value))
                return self

            def scard(self, key: str) -> MockPipeline:
                self.operations.append(("scard", key))
                return self

            def llen(self, key: str) -> MockPipeline:
                self.operations.append(("llen", key))
                return self

            def lrange(self, key: str, start: int, stop: int) -> MockPipeline:
                self.operations.append(("lrange", key, start, stop))
                return self

            def exists(self, key: str) -> MockPipeline:
                self.operations.append(("exists", key))
                return self

            async def execute(self) -> list[Any]:
                results: list[Any] = []
                for op in self.operations:
                    if op[0] == "rpush":
                        _, key, value = op
                        if key not in self.redis._data["lists"]:
                            self.redis._data["lists"][key] = []
                        self.redis._data["lists"][key].append(value)
                        results.append(len(self.redis._data["lists"][key]))
                    elif op[0] == "spop":
                        _, key = op
                        if key in self.redis._data["sets"] and self.redis._data["sets"][key]:
                            value = self.redis._data["sets"][key].pop()
                            results.append(value)
                        else:
                            results.append(None)
                    elif op[0] == "delete":
                        _, key = op
                        deleted = 0
                        for storage in self.redis._data.values():
                            if key in storage:
                                del storage[key]
                                deleted = 1
                        results.append(deleted)
                    elif op[0] == "expire":
                        results.append(True)
                    elif op[0] == "hset":
                        _, key, field, value = op
                        if key not in self.redis._data["hashes"]:
                            self.redis._data["hashes"][key] = {}
                        self.redis._data["hashes"][key][field] = value
                        results.append(1)
                    elif op[0] == "sadd":
                        _, key, value = op
                        if key not in self.redis._data["sets"]:
                            self.redis._data["sets"][key] = set()
                        if value not in self.redis._data["sets"][key]:
                            self.redis._data["sets"][key].add(value)
                            results.append(1)
                        else:
                            results.append(0)
                    elif op[0] == "set":
                        _, key, value = op
                        self.redis._data["strings"][key] = value
                        results.append("OK")
                    elif op[0] == "setex":
                        _, key, seconds, value = op
                        self.redis._data["strings"][key] = value
                        # We don't actually implement expiry in the mock
                        results.append("OK")
                    elif op[0] == "scard":
                        _, key = op
                        results.append(len(self.redis._data["sets"].get(key, set())))
                    elif op[0] == "llen":
                        _, key = op
                        results.append(len(self.redis._data["lists"].get(key, [])))
                    elif op[0] == "lrange":
                        _, key, start, stop = op
                        data = self.redis._data["lists"].get(key, [])
                        # Ensure start and stop are integers
                        start_idx = int(start) if isinstance(start, int | str) else 0
                        stop_idx = int(stop) if isinstance(stop, int | str) else -1
                        results.append(
                            data[start_idx : stop_idx + 1] if stop_idx != -1 else data[start_idx:]
                        )
                    elif op[0] == "exists":
                        _, key = op
                        exists = any(key in storage for storage in self.redis._data.values())
                        results.append(1 if exists else 0)
                return results

        mock_redis.create_transaction_pipeline = AsyncMock(
            side_effect=lambda: MockPipeline(mock_redis)
        )

        return mock_redis

    @pytest.fixture
    def settings(self) -> Settings:
        """Create test settings."""
        return Settings(redis_transaction_retries=3)

    @pytest.fixture
    async def batch_tracker(
        self, redis_client: AsyncMock, settings: Settings
    ) -> DefaultBatchEssayTracker:
        """Create batch tracker with mocked Redis."""
        # Create Redis coordinator with mocked Redis client
        redis_coordinator = RedisBatchCoordinator(
            redis_client=redis_client,
            settings=settings,
        )

        # Mock persistence (we're not testing database interactions)
        from unittest.mock import AsyncMock

        mock_persistence = AsyncMock(spec=BatchTrackerPersistence)
        mock_persistence.get_batch_from_database = AsyncMock(return_value=None)
        mock_persistence.persist_batch_expectation = AsyncMock()

        return DefaultBatchEssayTracker(
            persistence=mock_persistence,
            redis_coordinator=redis_coordinator,
        )

    @pytest.fixture
    async def coordination_handler(
        self,
        batch_tracker: DefaultBatchEssayTracker,
    ) -> tuple[DefaultBatchCoordinationHandler, AsyncMock]:
        """Create coordination handler with mocked dependencies."""
        from unittest.mock import AsyncMock

        # Mock repository and event publisher (we're testing coordination logic)
        mock_repository = AsyncMock()
        mock_repository.create_essay_records_batch = AsyncMock()

        mock_event_publisher = AsyncMock(spec=DefaultEventPublisher)
        mock_event_publisher.publish_batch_essays_ready = AsyncMock()

        handler = DefaultBatchCoordinationHandler(
            batch_tracker=batch_tracker,
            repository=mock_repository,
            event_publisher=mock_event_publisher,
        )

        return handler, mock_event_publisher

    async def test_validation_failure_before_batch_registration_completes_batch(
        self,
        batch_tracker: DefaultBatchEssayTracker,
        coordination_handler: tuple[DefaultBatchCoordinationHandler, AsyncMock],
        redis_client: AsyncMock,
    ) -> None:
        """
        Test the race condition fix:
        1. Validation failure arrives BEFORE batch registration
        2. Batch registration processes pending failure
        3. Batch completes immediately with 0 ready essays and 1 failure
        """
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

        # Unpack handler and mock event publisher
        handler, mock_event_publisher = coordination_handler

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
        assert is_completed is True

        # Verify BatchEssaysReady event was published
        mock_event_publisher.publish_batch_essays_ready.assert_called_once()
        call_args = mock_event_publisher.publish_batch_essays_ready.call_args
        ready_event = call_args.kwargs["event_data"]

        assert isinstance(ready_event, BatchEssaysReady)
        assert ready_event.batch_id == batch_id
        assert len(ready_event.ready_essays) == 0  # No successful essays
        assert ready_event.validation_failures is not None
        assert len(ready_event.validation_failures) == 1  # One validation failure
        assert (
            ready_event.validation_failures[0].file_upload_id == validation_failure.file_upload_id
        )

        # Verify batch state in Redis
        slots_key = f"batch:{batch_id}:available_slots"
        available_slots = await redis_client.scard(slots_key)
        assert available_slots == 0  # All slots consumed by failure

        failures_key = f"batch:{batch_id}:validation_failures"
        failure_count = await redis_client.llen(failures_key)
        assert failure_count == 1  # Failure was recorded

    async def test_multiple_pending_failures_all_processed_on_registration(
        self,
        batch_tracker: DefaultBatchEssayTracker,
        coordination_handler: tuple[DefaultBatchCoordinationHandler, AsyncMock],
        redis_client: AsyncMock,
    ) -> None:
        """Test that multiple pending failures are all processed when batch is registered."""
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

        # Unpack handler and mock event publisher
        handler, mock_event_publisher = coordination_handler
        
        # Track published events
        published_events = []
        original_publish = mock_event_publisher.publish_batch_essays_ready

        async def capture_publish(event_data: Any, correlation_id: UUID) -> None:
            published_events.append(event_data)
            await original_publish(event_data, correlation_id)

        mock_event_publisher.publish_batch_essays_ready = capture_publish

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
        assert ready_event.batch_id == batch_id
        assert len(ready_event.ready_essays) == 0  # All failed
        assert len(ready_event.validation_failures) == 3  # All 3 failures recorded

        # Verify all failures are in the validation failures list
        failure_ids = {f.file_upload_id for f in ready_event.validation_failures}
        expected_ids = {f.file_upload_id for f in validation_failures}
        assert failure_ids == expected_ids

    async def test_mixed_scenario_pending_and_normal_failures(
        self,
        batch_tracker: DefaultBatchEssayTracker,
        coordination_handler: tuple[DefaultBatchCoordinationHandler, AsyncMock],
        redis_client: AsyncMock,
    ) -> None:
        """Test scenario with both pending failures (before registration) and normal failures (after)."""
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

        # Unpack handler and mock event publisher
        handler, mock_event_publisher = coordination_handler
        
        # Register batch (processes 1 pending failure, 2 slots remain)
        await handler.handle_batch_essays_registered(
            event_data=batch_registration,
            correlation_id=correlation_id,
        )

        # Verify batch is NOT complete yet (1 failure, 2 slots remaining)
        completed_key = f"batch:{batch_id}:completed"
        is_completed = await redis_client.exists(completed_key)
        assert is_completed is False

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

        # Track completion event
        completion_event = None
        original_publish = mock_event_publisher.publish_batch_essays_ready

        async def capture_publish(event_data: Any, correlation_id: UUID) -> None:
            nonlocal completion_event
            completion_event = event_data
            await original_publish(event_data, correlation_id)

        mock_event_publisher.publish_batch_essays_ready = capture_publish

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
