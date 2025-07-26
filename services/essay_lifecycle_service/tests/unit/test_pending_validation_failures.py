"""
Unit tests for pending validation failures handling in Essay Lifecycle Service.

Tests the race condition fix where validation failures arrive before batch registration.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.error_enums import FileValidationErrorCode
from common_core.events.batch_coordination_events import (
    BatchEssaysRegistered,
)
from common_core.events.file_events import EssayValidationFailedV1
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from common_core.models.error_models import ErrorDetail

from services.essay_lifecycle_service.implementations.batch_coordination_handler_impl import (
    DefaultBatchCoordinationHandler,
)
from services.essay_lifecycle_service.implementations.batch_essay_tracker_impl import (
    DefaultBatchEssayTracker,
)
from services.essay_lifecycle_service.implementations.batch_tracker_persistence import (
    BatchTrackerPersistence,
)
from services.essay_lifecycle_service.implementations.redis_batch_coordinator import (
    RedisBatchCoordinator,
)


class TestPendingValidationFailures:
    """Test pending validation failures handling to fix race conditions."""

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.rpush = AsyncMock()
        mock.lrange = AsyncMock(return_value=[])
        mock.expire = AsyncMock()
        mock.delete_key = AsyncMock()
        mock.scard = AsyncMock(return_value=0)
        mock.llen = AsyncMock(return_value=0)
        mock.hlen = AsyncMock(return_value=0)
        mock.hget = AsyncMock(return_value=None)
        mock.exists = AsyncMock(return_value=False)
        mock.create_transaction_pipeline = AsyncMock()
        return mock

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        settings = MagicMock()
        settings.redis_transaction_retries = 3
        return settings

    @pytest.fixture
    def redis_coordinator(
        self, mock_redis_client: AsyncMock, mock_settings: MagicMock
    ) -> RedisBatchCoordinator:
        """Create Redis coordinator with mocks."""
        return RedisBatchCoordinator(redis_client=mock_redis_client, settings=mock_settings)

    @pytest.fixture
    def mock_persistence(self) -> AsyncMock:
        """Create mock persistence layer."""
        return AsyncMock(spec=BatchTrackerPersistence)

    @pytest.fixture
    def batch_tracker(
        self, mock_persistence: AsyncMock, redis_coordinator: RedisBatchCoordinator
    ) -> DefaultBatchEssayTracker:
        """Create batch tracker with mocks."""
        return DefaultBatchEssayTracker(
            persistence=mock_persistence, redis_coordinator=redis_coordinator
        )

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create mock repository."""
        mock = AsyncMock()
        mock.create_essay_records_batch = AsyncMock()
        return mock

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher."""
        mock = AsyncMock()
        mock.publish_batch_essays_ready = AsyncMock()
        return mock

    @pytest.fixture
    def coordination_handler(
        self,
        batch_tracker: DefaultBatchEssayTracker,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> DefaultBatchCoordinationHandler:
        """Create coordination handler with mocks."""
        return DefaultBatchCoordinationHandler(
            batch_tracker=batch_tracker,
            repository=mock_repository,
            event_publisher=mock_event_publisher,
        )

    async def test_validation_failure_before_batch_registration_stores_as_pending(
        self,
        mock_redis_client: AsyncMock,
        batch_tracker: DefaultBatchEssayTracker,
    ) -> None:
        """Test that validation failures arriving before batch registration are stored as pending."""
        # Arrange
        batch_id = "test-batch-123"
        correlation_id = uuid4()

        # Mock batch doesn't exist yet
        mock_redis_client.hgetall = AsyncMock(return_value={})

        # Create validation failure event
        validation_failure = EssayValidationFailedV1(
            batch_id=batch_id,
            file_upload_id="upload-456",
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
            raw_file_storage_id="raw-789",
            correlation_id=correlation_id,
        )

        # Act
        result = await batch_tracker.handle_validation_failure(validation_failure)

        # Assert
        assert result is None  # No batch ready event since batch doesn't exist
        
        # Verify pending failure was stored
        mock_redis_client.rpush.assert_called_once()
        call_args = mock_redis_client.rpush.call_args
        assert "pending_failures" in call_args[0][0]  # Key contains pending_failures
        assert batch_id in call_args[0][0]  # Key contains batch_id
        
        # Verify TTL was set
        mock_redis_client.expire.assert_called_once()

    async def test_batch_registration_processes_pending_failures(
        self,
        mock_redis_client: AsyncMock,
        coordination_handler: DefaultBatchCoordinationHandler,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that batch registration processes pending validation failures."""
        # Arrange
        batch_id = "test-batch-123"
        correlation_id = uuid4()
        
        # Mock batch doesn't exist initially
        mock_redis_client.hgetall = AsyncMock(return_value={})
        mock_redis_client.scard = AsyncMock(return_value=0)
        
        # Mock pending failures exist
        pending_failure = {
            "batch_id": batch_id,
            "file_upload_id": "upload-456",
            "original_file_name": "essay1.pdf",
            "validation_error_code": FileValidationErrorCode.EMPTY_CONTENT.value,
            "validation_error_detail": {
                "error_code": "EMPTY_CONTENT",
                "message": "File is empty",
                "correlation_id": str(correlation_id),
                "timestamp": datetime.now(UTC).isoformat(),
                "service": "file_service",
                "operation": "validate",
                "details": {},
            },
            "file_size_bytes": 0,
            "raw_file_storage_id": "raw-789",
            "correlation_id": str(correlation_id),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        mock_redis_client.lrange = AsyncMock(return_value=[json.dumps(pending_failure).encode()])
        
        # Mock transaction pipeline
        pipeline = AsyncMock()
        pipeline.multi = AsyncMock()
        pipeline.sadd = AsyncMock()
        pipeline.hset = AsyncMock()
        pipeline.setex = AsyncMock()
        pipeline.rpush = AsyncMock()
        pipeline.spop = AsyncMock()
        pipeline.delete_key = AsyncMock()
        pipeline.expire = AsyncMock()
        pipeline.execute = AsyncMock(return_value=[True])
        mock_redis_client.create_transaction_pipeline = AsyncMock(return_value=pipeline)

        # Create batch registration event with 1 essay
        batch_registered = BatchEssaysRegistered(
            batch_id=batch_id,
            essay_ids=["essay-001"],  # Only 1 essay expected
            expected_essay_count=1,
            user_id="test-user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_type="batch", entity_id=batch_id),
            ),
            course_code=CourseCode.ENG5,
            essay_instructions="Write an essay",
        )

        # Mock batch status after registration to indicate completion
        # Since we have 1 essay slot and 1 validation failure, batch is complete
        mock_redis_client.hgetall = AsyncMock(
            side_effect=[
                {},  # First call: batch doesn't exist
                {  # Second call: batch exists after registration
                    b"batch_id": batch_id.encode(),
                    b"course_code": b"ENG5",
                    b"expected_count": b"1",
                },
            ]
        )
        
        # Mock completion check to return True (1 failure = 1 expected = complete)
        mock_redis_client.scard = AsyncMock(return_value=0)  # 0 available slots
        mock_redis_client.llen = AsyncMock(return_value=1)  # 1 failure
        mock_redis_client.hlen = AsyncMock(return_value=0)  # 0 assignments
        mock_redis_client.hget = AsyncMock(return_value=b"1")  # expected_count = 1
        mock_redis_client.exists = AsyncMock(return_value=False)  # not already completed
        
        # Mock setting completion flag
        mock_redis_client.set_if_not_exists = AsyncMock(return_value=True)

        # Act
        result = await coordination_handler.handle_batch_essays_registered(
            event_data=batch_registered, correlation_id=correlation_id
        )

        # Assert
        assert result is True
        
        # Verify pending failures were processed
        # Should have called lrange to get pending failures
        lrange_calls = [call for call in mock_redis_client.lrange.call_args_list 
                       if "pending_failures" in str(call)]
        assert len(lrange_calls) > 0
        
        # Verify batch ready event was published due to immediate completion
        mock_event_publisher.publish_batch_essays_ready.assert_called_once()
        published_event = mock_event_publisher.publish_batch_essays_ready.call_args[1]["event_data"]
        assert published_event.batch_id == batch_id
        assert len(published_event.ready_essays) == 0  # No successful essays
        assert len(published_event.validation_failures) == 1  # One validation failure

    async def test_no_pending_failures_normal_batch_registration(
        self,
        mock_redis_client: AsyncMock,
        coordination_handler: DefaultBatchCoordinationHandler,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test normal batch registration when no pending failures exist."""
        # Arrange
        batch_id = "test-batch-456"
        correlation_id = uuid4()
        
        # Mock no pending failures
        mock_redis_client.lrange = AsyncMock(return_value=[])
        
        # Mock transaction pipeline
        pipeline = AsyncMock()
        pipeline.multi = AsyncMock()
        pipeline.sadd = AsyncMock()
        pipeline.hset = AsyncMock()
        pipeline.setex = AsyncMock()
        pipeline.execute = AsyncMock(return_value=[True])
        mock_redis_client.create_transaction_pipeline = AsyncMock(return_value=pipeline)

        # Create batch registration event
        batch_registered = BatchEssaysRegistered(
            batch_id=batch_id,
            essay_ids=["essay-001", "essay-002"],
            expected_essay_count=2,
            user_id="test-user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_type="batch", entity_id=batch_id),
            ),
            course_code=CourseCode.ENG5,
            essay_instructions="Write an essay",
        )

        # Mock batch status - not complete yet
        mock_redis_client.hgetall = AsyncMock(
            return_value={
                b"batch_id": batch_id.encode(),
                b"course_code": b"ENG5",
                b"expected_count": b"2",
            }
        )
        mock_redis_client.scard = AsyncMock(return_value=2)  # 2 available slots
        mock_redis_client.llen = AsyncMock(return_value=0)  # 0 failures
        mock_redis_client.hlen = AsyncMock(return_value=0)  # 0 assignments

        # Act
        result = await coordination_handler.handle_batch_essays_registered(
            event_data=batch_registered, correlation_id=correlation_id
        )

        # Assert
        assert result is True
        
        # Verify no batch ready event was published (batch not complete)
        mock_event_publisher.publish_batch_essays_ready.assert_not_called()