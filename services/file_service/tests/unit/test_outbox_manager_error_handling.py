"""
Unit tests for OutboxManager error handling scenarios.

Focuses on defensive error handling paths and graceful degradation
following TRUE OUTBOX PATTERN architectural principles.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from common_core.events.envelope import EventEnvelope
from common_core.events.file_events import EssayContentProvisionedV1
from huleedu_service_libs.error_handling import HuleEduError

from services.file_service.config import Settings
from services.file_service.implementations.outbox_manager import OutboxManager


@pytest.fixture
def test_settings() -> Settings:
    """Test settings."""
    settings: Mock = Mock(spec=Settings)
    settings.SERVICE_NAME = "file_service"
    return settings


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Mock Redis client."""
    return AsyncMock()


@pytest.fixture
def sample_event_envelope() -> EventEnvelope:
    """Sample event envelope for testing."""
    correlation_id: UUID = uuid4()

    # Create properly typed event data
    event_data = EssayContentProvisionedV1(
        batch_id="test-batch-123",
        file_upload_id="test-file-123",
        original_file_name="test_essay.txt",
        raw_file_storage_id="raw-storage-123",
        text_storage_id="text-storage-123",
        file_size_bytes=1024,
        content_md5_hash="test-hash-123",
        timestamp=datetime.now(timezone.utc),
    )

    return EventEnvelope(
        event_type="file.essay.content.provisioned.v1",
        source_service="file_service",
        correlation_id=correlation_id,
        data=event_data,
    )


class TestOutboxManagerErrorHandling:
    """Test OutboxManager error handling scenarios."""

    async def test_unconfigured_repository_raises_error(
        self,
        test_settings: Settings,
        mock_redis_client: AsyncMock,
        sample_event_envelope: EventEnvelope,
    ) -> None:
        """Test that None repository raises proper HuleEduError."""
        # Given
        outbox_manager: OutboxManager = OutboxManager(
            outbox_repository=None,  # type: ignore
            redis_client=mock_redis_client,
            settings=test_settings,
        )

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="test_entity",
                aggregate_id="test-123",
                event_type="test.event.v1",
                event_data=sample_event_envelope,
                topic="test.topic",
            )

        # Verify error details
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.service == "file_service"
        assert error_detail.operation == "publish_to_outbox"
        assert "Outbox repository not configured" in error_detail.message
        assert error_detail.correlation_id == sample_event_envelope.correlation_id

    async def test_repository_exception_wrapped_with_correlation_id(
        self,
        test_settings: Settings,
        mock_redis_client: AsyncMock,
        sample_event_envelope: EventEnvelope,
    ) -> None:
        """Test repository exceptions are wrapped with proper correlation ID."""
        # Given
        mock_repository: AsyncMock = AsyncMock()
        mock_repository.add_event.side_effect = Exception("Database connection lost")

        outbox_manager: OutboxManager = OutboxManager(
            outbox_repository=mock_repository,
            redis_client=mock_redis_client,
            settings=test_settings,
        )

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="test_entity",
                aggregate_id="test-456",
                event_type="test.event.v1",
                event_data=sample_event_envelope,
                topic="test.topic",
            )

        # Verify wrapped error details
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.service == "file_service"
        assert error_detail.operation == "publish_to_outbox"
        assert "Failed to store event in outbox" in error_detail.message
        assert error_detail.correlation_id == sample_event_envelope.correlation_id

    async def test_correlation_id_extraction_from_dict_event_data(
        self,
        test_settings: Settings,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test correlation ID extraction from dict event data."""
        # Given
        mock_repository: AsyncMock = AsyncMock()
        mock_repository.add_event.side_effect = Exception("Test exception")

        outbox_manager: OutboxManager = OutboxManager(
            outbox_repository=mock_repository,
            redis_client=mock_redis_client,
            settings=test_settings,
        )

        test_correlation_id: UUID = uuid4()
        dict_event_data: dict[str, Any] = {
            "correlation_id": str(test_correlation_id),
            "data": "test",
        }

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="test_entity",
                aggregate_id="test-789",
                event_type="test.event.v1",
                event_data=dict_event_data,
                topic="test.topic",
            )

        # Verify correlation ID extracted from dict
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.correlation_id == test_correlation_id

    async def test_correlation_id_fallback_for_invalid_data(
        self,
        test_settings: Settings,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test correlation ID fallback when extraction fails."""
        # Given
        mock_repository: AsyncMock = AsyncMock()
        mock_repository.add_event.side_effect = Exception("Test exception")

        outbox_manager: OutboxManager = OutboxManager(
            outbox_repository=mock_repository,
            redis_client=mock_redis_client,
            settings=test_settings,
        )

        invalid_event_data: dict[str, str] = {"correlation_id": "invalid-uuid-format"}

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="test_entity",
                aggregate_id="test-999",
                event_type="test.event.v1",
                event_data=invalid_event_data,
                topic="test.topic",
            )

        # Verify fallback to default UUID
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.correlation_id == UUID("00000000-0000-0000-0000-000000000000")

    async def test_redis_notification_failure_graceful_degradation(
        self,
        test_settings: Settings,
        sample_event_envelope: EventEnvelope,
    ) -> None:
        """Test Redis notification failure doesn't prevent outbox storage."""
        # Given
        mock_repository: AsyncMock = AsyncMock()
        mock_repository.add_event.return_value = uuid4()

        mock_redis_client: AsyncMock = AsyncMock()
        mock_redis_client.lpush.side_effect = Exception("Redis connection timeout")

        outbox_manager: OutboxManager = OutboxManager(
            outbox_repository=mock_repository,
            redis_client=mock_redis_client,
            settings=test_settings,
        )

        # When - This should NOT raise an exception despite Redis failure
        await outbox_manager.publish_to_outbox(
            aggregate_type="test_entity",
            aggregate_id="test-redis-fail",
            event_type="test.event.v1",
            event_data=sample_event_envelope,
            topic="test.topic",
        )

        # Then
        # Verify outbox storage succeeded despite Redis failure
        mock_repository.add_event.assert_called_once()

        # Verify Redis notification was attempted but failed gracefully
        mock_redis_client.lpush.assert_called_once_with("outbox:wake:file_service", "1")

    async def test_custom_partition_key_from_metadata(
        self,
        test_settings: Settings,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test custom partition key extraction from event metadata."""
        # Given
        mock_repository = AsyncMock()
        mock_repository.add_event.return_value = uuid4()

        outbox_manager = OutboxManager(
            outbox_repository=mock_repository,
            redis_client=mock_redis_client,
            settings=test_settings,
        )

        # Create event with custom partition key in metadata
        correlation_id: UUID = uuid4()

        # Create properly typed event data
        event_data = EssayContentProvisionedV1(
            batch_id="test-batch-partition",
            file_upload_id="test-file-partition",
            original_file_name="partition_test.txt",
            raw_file_storage_id="raw-partition-123",
            text_storage_id="text-partition-123",
            file_size_bytes=2048,
            content_md5_hash="partition-hash-123",
            timestamp=datetime.now(timezone.utc),
        )

        event_with_metadata: EventEnvelope = EventEnvelope(
            event_type="file.essay.content.provisioned.v1",
            source_service="file_service",
            correlation_id=correlation_id,
            data=event_data,
            metadata={"partition_key": "custom-partition-key"},
        )

        # When
        await outbox_manager.publish_to_outbox(
            aggregate_type="test_entity",
            aggregate_id="test-partition",
            event_type="test.event.v1",
            event_data=event_with_metadata,
            topic="test.topic",
        )

        # Then
        # Verify custom partition key was used
        mock_repository.add_event.assert_called_once()
        call_args: Any = mock_repository.add_event.call_args
        assert call_args.kwargs["event_key"] == "custom-partition-key"

    async def test_non_pydantic_event_data_validation(
        self,
        test_settings: Settings,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test validation error for non-Pydantic event data."""
        # Given
        mock_repository: AsyncMock = AsyncMock()
        outbox_manager: OutboxManager = OutboxManager(
            outbox_repository=mock_repository,
            redis_client=mock_redis_client,
            settings=test_settings,
        )

        # When/Then - ValueError is caught and wrapped as HuleEduError by OutboxManager
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="test_entity",
                aggregate_id="test-invalid",
                event_type="test.event.v1",
                event_data="invalid-string-data",  # Not a Pydantic model
                topic="test.topic",
            )

        # Verify the wrapped error contains the original validation message
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.service == "file_service"
        assert error_detail.operation == "publish_to_outbox"
        assert "Failed to store event in outbox" in error_detail.message
        assert "ValueError" in error_detail.message

    async def test_successful_outbox_storage_with_topic_injection(
        self,
        test_settings: Settings,
        mock_redis_client: AsyncMock,
        sample_event_envelope: EventEnvelope,
    ) -> None:
        """Test successful outbox storage injects topic into serialized data."""
        # Given
        mock_repository = AsyncMock()
        mock_repository.add_event.return_value = uuid4()

        outbox_manager = OutboxManager(
            outbox_repository=mock_repository,
            redis_client=mock_redis_client,
            settings=test_settings,
        )

        # When
        await outbox_manager.publish_to_outbox(
            aggregate_type="test_entity",
            aggregate_id="test-success",
            event_type="test.event.v1",
            event_data=sample_event_envelope,
            topic="test.topic.success",
        )

        # Then
        mock_repository.add_event.assert_called_once()
        call_args: Any = mock_repository.add_event.call_args

        # Verify topic was added to serialized data
        serialized_data: dict[str, Any] = call_args.kwargs["event_data"]
        assert serialized_data["topic"] == "test.topic.success"

        # Verify other parameters
        assert call_args.kwargs["aggregate_id"] == "test-success"
        assert call_args.kwargs["aggregate_type"] == "test_entity"
        assert call_args.kwargs["event_type"] == "test.event.v1"
        assert call_args.kwargs["topic"] == "test.topic.success"
        assert call_args.kwargs["event_key"] == "test-success"  # Default to aggregate_id
