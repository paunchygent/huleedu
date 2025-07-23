"""
Unit tests for file management event publishing functionality.

Tests the DefaultEventPublisher implementation for BatchFileAddedV1 and
BatchFileRemovedV1 events with proper mocking of the KafkaBus.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from common_core.events.file_management_events import BatchFileAddedV1, BatchFileRemovedV1

from services.file_service.config import Settings
from services.file_service.implementations.event_publisher_impl import DefaultEventPublisher


class TestDefaultEventPublisherFileManagement:
    """Test file management event publishing functionality."""

    @pytest.fixture
    def mock_kafka_bus(self) -> AsyncMock:
        """Create a mocked KafkaBus for testing."""
        return AsyncMock()

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Create a mocked Redis client for testing."""
        return AsyncMock()

    @pytest.fixture
    def mock_settings(self) -> Mock:
        """Create mock settings for testing."""
        settings = Mock(spec=Settings)
        settings.SERVICE_NAME = "file-service"
        settings.BATCH_FILE_ADDED_TOPIC = "huleedu.file.batch.file.added.v1"
        settings.BATCH_FILE_REMOVED_TOPIC = "huleedu.file.batch.file.removed.v1"
        return settings

    @pytest.fixture
    def event_publisher(
        self, mock_kafka_bus: AsyncMock, mock_redis_client: AsyncMock, mock_settings: Mock
    ) -> DefaultEventPublisher:
        """Create DefaultEventPublisher instance with mocked dependencies."""
        return DefaultEventPublisher(mock_kafka_bus, mock_settings, mock_redis_client)

    async def test_publish_batch_file_added_v1_success(
        self,
        event_publisher: DefaultEventPublisher,
        mock_kafka_bus: AsyncMock,
        mock_redis_client: AsyncMock,
        mock_settings: Mock,
    ) -> None:
        """Test successful publishing of BatchFileAddedV1 event."""
        # Arrange
        correlation_id = uuid.uuid4()
        event_data = BatchFileAddedV1(
            batch_id="test-batch-123",
            file_upload_id="file-upload-456",
            filename="test_essay.txt",
            user_id="user-789",
        )

        # Act
        await event_publisher.publish_batch_file_added_v1(event_data, correlation_id)

        # Assert
        mock_kafka_bus.publish.assert_called_once()
        call_args = mock_kafka_bus.publish.call_args

        # Verify topic
        assert call_args.kwargs["topic"] == mock_settings.BATCH_FILE_ADDED_TOPIC

        # Verify envelope structure
        envelope = call_args.kwargs["envelope"]
        assert envelope.event_type == mock_settings.BATCH_FILE_ADDED_TOPIC
        assert envelope.source_service == mock_settings.SERVICE_NAME
        assert envelope.correlation_id == correlation_id
        assert envelope.data == event_data

        # Verify Redis publish was called
        mock_redis_client.publish_user_notification.assert_called_once_with(
            user_id="user-789",
            event_type="batch_file_added",
            data={
                "batch_id": "test-batch-123",
                "file_upload_id": "file-upload-456",
                "filename": "test_essay.txt",
                "timestamp": event_data.timestamp.isoformat(),
            },
        )

    async def test_publish_batch_file_added_v1_with_correlation_id(
        self,
        event_publisher: DefaultEventPublisher,
        mock_kafka_bus: AsyncMock,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test publishing BatchFileAddedV1 event with correlation_id."""
        # Arrange
        test_correlation_id = uuid4()
        event_data = BatchFileAddedV1(
            batch_id="test-batch-123",
            file_upload_id="file-upload-456",
            filename="test_essay.txt",
            user_id="user-789",
        )

        # Act
        await event_publisher.publish_batch_file_added_v1(event_data, test_correlation_id)

        # Assert
        mock_kafka_bus.publish.assert_called_once()
        envelope = mock_kafka_bus.publish.call_args.kwargs["envelope"]
        assert envelope.correlation_id == test_correlation_id

        # Verify Redis publish was called
        mock_redis_client.publish_user_notification.assert_called_once()

    async def test_publish_batch_file_added_v1_kafka_error(
        self,
        event_publisher: DefaultEventPublisher,
        mock_kafka_bus: AsyncMock,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test error handling when Kafka publishing fails for BatchFileAddedV1."""
        # Arrange
        event_data = BatchFileAddedV1(
            batch_id="test-batch-123",
            file_upload_id="file-upload-456",
            filename="test_essay.txt",
            user_id="user-789",
        )
        mock_kafka_bus.publish.side_effect = Exception("Kafka connection failed")

        # Act & Assert
        with pytest.raises(Exception, match="Kafka connection failed"):
            await event_publisher.publish_batch_file_added_v1(event_data, uuid4())

    async def test_publish_batch_file_removed_v1_success(
        self,
        event_publisher: DefaultEventPublisher,
        mock_kafka_bus: AsyncMock,
        mock_redis_client: AsyncMock,
        mock_settings: Mock,
    ) -> None:
        """Test successful publishing of BatchFileRemovedV1 event."""
        # Arrange
        correlation_id = uuid.uuid4()
        event_data = BatchFileRemovedV1(
            batch_id="test-batch-123",
            file_upload_id="file-upload-456",
            filename="test_essay.txt",
            user_id="user-789",
        )

        # Act
        await event_publisher.publish_batch_file_removed_v1(event_data, correlation_id)

        # Assert
        mock_kafka_bus.publish.assert_called_once()
        call_args = mock_kafka_bus.publish.call_args

        # Verify topic
        assert call_args.kwargs["topic"] == mock_settings.BATCH_FILE_REMOVED_TOPIC

        # Verify envelope structure
        envelope = call_args.kwargs["envelope"]
        assert envelope.event_type == mock_settings.BATCH_FILE_REMOVED_TOPIC
        assert envelope.source_service == mock_settings.SERVICE_NAME
        assert envelope.correlation_id == correlation_id
        assert envelope.data == event_data

        # Verify Redis publish was called
        mock_redis_client.publish_user_notification.assert_called_once_with(
            user_id="user-789",
            event_type="batch_file_removed",
            data={
                "batch_id": "test-batch-123",
                "file_upload_id": "file-upload-456",
                "filename": "test_essay.txt",
                "timestamp": event_data.timestamp.isoformat(),
            },
        )

    async def test_publish_batch_file_removed_v1_with_correlation_id(
        self,
        event_publisher: DefaultEventPublisher,
        mock_kafka_bus: AsyncMock,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test publishing BatchFileRemovedV1 event with correlation_id."""
        # Arrange
        test_correlation_id = uuid4()
        event_data = BatchFileRemovedV1(
            batch_id="test-batch-123",
            file_upload_id="file-upload-456",
            filename="test_essay.txt",
            user_id="user-789",
        )

        # Act
        await event_publisher.publish_batch_file_removed_v1(event_data, test_correlation_id)

        # Assert
        mock_kafka_bus.publish.assert_called_once()
        envelope = mock_kafka_bus.publish.call_args.kwargs["envelope"]
        assert envelope.correlation_id == test_correlation_id

        # Verify Redis publish was called
        mock_redis_client.publish_user_notification.assert_called_once()

    async def test_publish_batch_file_removed_v1_kafka_error(
        self,
        event_publisher: DefaultEventPublisher,
        mock_kafka_bus: AsyncMock,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test error handling when Kafka publishing fails for BatchFileRemovedV1."""
        # Arrange
        event_data = BatchFileRemovedV1(
            batch_id="test-batch-123",
            file_upload_id="file-upload-456",
            filename="test_essay.txt",
            user_id="user-789",
        )
        mock_kafka_bus.publish.side_effect = Exception("Kafka connection failed")

        # Act & Assert
        with pytest.raises(Exception, match="Kafka connection failed"):
            await event_publisher.publish_batch_file_removed_v1(event_data, uuid4())

    async def test_event_data_construction(self) -> None:
        """Test that event data models construct correctly with all required fields."""
        # Test BatchFileAddedV1
        added_event = BatchFileAddedV1(
            batch_id="batch-123",
            file_upload_id="file-upload-456",
            filename="test.txt",
            user_id="user-789",
        )
        assert added_event.event == "batch.file.added"
        assert added_event.batch_id == "batch-123"
        assert added_event.file_upload_id == "file-upload-456"
        assert added_event.filename == "test.txt"
        assert added_event.user_id == "user-789"
        assert added_event.timestamp is not None
        assert isinstance(added_event.correlation_id, UUID)  # Default uuid4()

        # Test BatchFileRemovedV1
        removed_event = BatchFileRemovedV1(
            batch_id="batch-123",
            file_upload_id="file-upload-456",
            filename="test.txt",
            user_id="user-789",
        )
        assert removed_event.event == "batch.file.removed"
        assert removed_event.batch_id == "batch-123"
        assert removed_event.file_upload_id == "file-upload-456"
        assert removed_event.filename == "test.txt"
        assert removed_event.user_id == "user-789"
        assert removed_event.timestamp is not None
        assert isinstance(removed_event.correlation_id, UUID)  # Default uuid4()
