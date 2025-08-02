"""
Unit tests for DefaultEventPublisher with outbox pattern integration.

Tests focus on verifying the correct interaction with the outbox repository,
Redis notifications for batch events, and error handling.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest
from common_core.events.file_events import EssayContentProvisionedV1, EssayValidationFailedV1
from common_core.events.file_management_events import BatchFileAddedV1, BatchFileRemovedV1
from huleedu_service_libs.protocols import KafkaPublisherProtocol
from sqlalchemy.ext.asyncio import AsyncSession

from services.file_service.config import Settings
from services.file_service.implementations.event_publisher_impl import DefaultEventPublisher
from services.file_service.implementations.outbox_manager import OutboxManager


class FakeOutboxRepository:
    """Fake implementation of OutboxRepositoryProtocol for testing."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.add_event_calls: list[dict[str, Any]] = []
        self.should_fail = False
        self.failure_message = "Outbox storage failed"

    async def add_event(
        self,
        aggregate_id: str,
        aggregate_type: str,
        event_type: str,
        event_data: dict[str, Any],
        topic: str,
        event_key: str | None = None,
        session: AsyncSession | None = None,
    ) -> UUID:
        """Store event in fake outbox."""
        if self.should_fail:
            raise Exception(self.failure_message)

        event_id = uuid4()
        call_data = {
            "id": event_id,
            "aggregate_id": aggregate_id,
            "aggregate_type": aggregate_type,
            "event_type": event_type,
            "event_data": event_data,
            "topic": topic,
            "event_key": event_key,
            "session": session,
        }
        self.add_event_calls.append(call_data)
        self.events.append(call_data)
        return event_id


@pytest.fixture
def test_settings() -> Settings:
    """Test settings with configured topics."""
    settings = Mock(spec=Settings)
    settings.SERVICE_NAME = "file-service"
    settings.ESSAY_CONTENT_PROVISIONED_TOPIC = "file.essay.content.provisioned.v1"
    settings.ESSAY_VALIDATION_FAILED_TOPIC = "file.essay.validation.failed.v1"
    settings.BATCH_FILE_ADDED_TOPIC = "file.batch.file.added.v1"
    settings.BATCH_FILE_REMOVED_TOPIC = "file.batch.file.removed.v1"
    return settings


@pytest.fixture
def fake_kafka() -> Mock:
    """Fake Kafka publisher (not used with outbox pattern)."""
    return Mock(spec=KafkaPublisherProtocol)


@pytest.fixture
def fake_outbox() -> FakeOutboxRepository:
    """Fake outbox repository for testing."""
    return FakeOutboxRepository()


@pytest.fixture
def mock_outbox_manager() -> AsyncMock:
    """Mock OutboxManager for testing using protocol-based mocking."""
    return AsyncMock(spec=OutboxManager)


@pytest.fixture
def event_publisher(
    test_settings: Settings,
    mock_outbox_manager: AsyncMock,
) -> DefaultEventPublisher:
    """Create event publisher with mocked dependencies for TRUE OUTBOX PATTERN testing."""
    return DefaultEventPublisher(
        outbox_manager=mock_outbox_manager,
        settings=test_settings,
    )


@pytest.fixture
def sample_correlation_id() -> UUID:
    """Sample correlation ID for testing."""
    return uuid4()


class TestDefaultEventPublisher:
    """Test DefaultEventPublisher behavior with outbox pattern."""

    async def test_publish_essay_content_provisioned_success(
        self,
        event_publisher: DefaultEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
    ) -> None:
        """Verify EssayContentProvisionedV1 event calls OutboxManager with correct parameters."""
        # Given
        event_data = EssayContentProvisionedV1(
            entity_id="batch-001",
            file_upload_id="file-123",
            original_file_name="test_essay.pdf",
            raw_file_storage_id="raw-456",
            text_storage_id="extracted-789",
            file_size_bytes=1024,
            content_md5_hash="abc123def456",
            timestamp=datetime.now(timezone.utc),
        )

        # When
        with patch("huleedu_service_libs.observability.inject_trace_context"):
            await event_publisher.publish_essay_content_provisioned(
                event_data, sample_correlation_id
            )

        # Then - Verify OutboxManager.publish_to_outbox was called with correct parameters
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        assert call_args.kwargs["aggregate_type"] == "file_upload"
        assert call_args.kwargs["aggregate_id"] == "file-123"
        assert call_args.kwargs["event_type"] == "file.essay.content.provisioned.v1"
        assert call_args.kwargs["topic"] == "file.essay.content.provisioned.v1"

        # Verify envelope structure in event_data parameter
        envelope = call_args.kwargs["event_data"]
        assert envelope.event_type == "file.essay.content.provisioned.v1"
        assert envelope.source_service == "file-service"
        assert envelope.correlation_id == sample_correlation_id
        assert envelope.data == event_data

    async def test_publish_essay_validation_failed_success(
        self,
        event_publisher: DefaultEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
    ) -> None:
        """Verify EssayValidationFailedV1 event calls OutboxManager with correct parameters."""
        # Given
        from common_core.error_enums import FileValidationErrorCode
        from common_core.models.error_models import ErrorDetail

        error_detail = ErrorDetail(
            error_code=FileValidationErrorCode.CONTENT_TOO_LONG,
            message="Content exceeds maximum allowed length",
            correlation_id=sample_correlation_id,
            timestamp=datetime.now(timezone.utc),
            service="file-service",
            operation="validate_content",
            details={"word_count": 5500, "max_allowed": 5000},
        )

        event_data = EssayValidationFailedV1(
            entity_id="batch-002",
            file_upload_id="file-456",
            original_file_name="invalid_essay.docx",
            raw_file_storage_id="raw-999",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_LONG,
            validation_error_detail=error_detail,
            file_size_bytes=2048,
            timestamp=datetime.now(timezone.utc),
        )

        # When
        with patch("huleedu_service_libs.observability.inject_trace_context"):
            await event_publisher.publish_essay_validation_failed(event_data, sample_correlation_id)

        # Then - Verify OutboxManager.publish_to_outbox was called with correct parameters
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        assert call_args.kwargs["aggregate_type"] == "file_upload"
        assert call_args.kwargs["aggregate_id"] == "file-456"
        assert call_args.kwargs["event_type"] == "file.essay.validation.failed.v1"
        assert call_args.kwargs["topic"] == "file.essay.validation.failed.v1"

        # Verify envelope structure in event_data parameter
        envelope = call_args.kwargs["event_data"]
        assert envelope.event_type == "file.essay.validation.failed.v1"
        assert envelope.source_service == "file-service"
        assert envelope.correlation_id == sample_correlation_id
        assert envelope.data == event_data

    async def test_publish_batch_file_added_success(
        self,
        event_publisher: DefaultEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
    ) -> None:
        """Verify BatchFileAddedV1 event calls OutboxManager with correct parameters."""
        # Given
        event_data = BatchFileAddedV1(
            batch_id="batch-789",
            file_upload_id="file-999",
            filename="student_essay.pdf",
            user_id="user-123",
            timestamp=datetime.now(timezone.utc),
        )

        # When
        with patch("huleedu_service_libs.observability.inject_trace_context"):
            await event_publisher.publish_batch_file_added_v1(event_data, sample_correlation_id)

        # Then - Verify OutboxManager.publish_to_outbox was called with correct parameters
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        assert call_args.kwargs["aggregate_type"] == "batch"
        assert call_args.kwargs["aggregate_id"] == "batch-789"
        assert call_args.kwargs["event_type"] == "file.batch.file.added.v1"
        assert call_args.kwargs["topic"] == "file.batch.file.added.v1"

        # Verify envelope structure in event_data parameter
        envelope = call_args.kwargs["event_data"]
        assert envelope.event_type == "file.batch.file.added.v1"
        assert envelope.source_service == "file-service"
        assert envelope.correlation_id == sample_correlation_id
        assert envelope.data == event_data

    async def test_publish_batch_file_removed_success(
        self,
        event_publisher: DefaultEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
    ) -> None:
        """Verify BatchFileRemovedV1 event calls OutboxManager with correct parameters."""
        # Given
        event_data = BatchFileRemovedV1(
            batch_id="batch-111",
            file_upload_id="file-222",
            filename="removed_essay.pdf",
            user_id="user-456",
            timestamp=datetime.now(timezone.utc),
        )

        # When
        with patch("huleedu_service_libs.observability.inject_trace_context"):
            await event_publisher.publish_batch_file_removed_v1(event_data, sample_correlation_id)

        # Then - Verify OutboxManager.publish_to_outbox was called with correct parameters
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        assert call_args.kwargs["aggregate_type"] == "batch"
        assert call_args.kwargs["aggregate_id"] == "batch-111"
        assert call_args.kwargs["event_type"] == "file.batch.file.removed.v1"
        assert call_args.kwargs["topic"] == "file.batch.file.removed.v1"

        # Verify envelope structure in event_data parameter
        envelope = call_args.kwargs["event_data"]
        assert envelope.event_type == "file.batch.file.removed.v1"
        assert envelope.source_service == "file-service"
        assert envelope.correlation_id == sample_correlation_id
        assert envelope.data == event_data

    async def test_outbox_failure_propagates_exception(
        self,
        event_publisher: DefaultEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
    ) -> None:
        """Verify that outbox storage failures are propagated as exceptions."""
        # Given
        mock_outbox_manager.publish_to_outbox.side_effect = Exception("Database connection lost")

        event_data = EssayContentProvisionedV1(
            entity_id="batch-fail",
            file_upload_id="file-fail",
            original_file_name="fail.pdf",
            raw_file_storage_id="raw-fail",
            text_storage_id="extracted-fail",
            file_size_bytes=1024,
            content_md5_hash="fail123hash",
            timestamp=datetime.now(timezone.utc),
        )

        # When/Then
        with pytest.raises(Exception) as exc_info:
            await event_publisher.publish_essay_content_provisioned(
                event_data, sample_correlation_id
            )

        assert "Database connection lost" in str(exc_info.value)
        mock_outbox_manager.publish_to_outbox.assert_called_once()

    async def test_trace_context_injection(
        self,
        event_publisher: DefaultEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
    ) -> None:
        """Verify trace context is injected into event metadata."""
        # Given
        event_data = EssayContentProvisionedV1(
            entity_id="batch-trace",
            file_upload_id="file-trace",
            original_file_name="trace.pdf",
            raw_file_storage_id="raw-trace",
            text_storage_id="extracted-trace",
            file_size_bytes=1024,
            content_md5_hash="trace123hash",
            timestamp=datetime.now(timezone.utc),
        )

        mock_inject = Mock()

        # When
        with patch("huleedu_service_libs.observability.inject_trace_context", mock_inject):
            await event_publisher.publish_essay_content_provisioned(
                event_data, sample_correlation_id
            )

        # Then - Verify trace context injection was called
        assert mock_inject.called
        # Verify inject_trace_context was called with the envelope metadata
        call_args = mock_inject.call_args[0]
        assert isinstance(call_args[0], dict)  # metadata dict

        # Verify OutboxManager was called (confirming the flow completed)
        mock_outbox_manager.publish_to_outbox.assert_called_once()

    async def test_event_envelope_serialization(
        self,
        event_publisher: DefaultEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
    ) -> None:
        """Verify event envelope is properly serialized with model_dump(mode='json')."""
        # Given
        from common_core.error_enums import FileValidationErrorCode
        from common_core.models.error_models import ErrorDetail

        timestamp = datetime.now(timezone.utc)

        error_detail = ErrorDetail(
            error_code=FileValidationErrorCode.UNKNOWN_VALIDATION_ERROR,
            message="Invalid file format",
            correlation_id=sample_correlation_id,
            timestamp=timestamp,
            service="file-service",
            operation="validate_content",
            details={"format": "corrupted"},
        )

        event_data = EssayValidationFailedV1(
            entity_id="batch-serial",
            file_upload_id="file-serial",
            original_file_name="serial.pdf",
            raw_file_storage_id="raw-serial",
            validation_error_code=FileValidationErrorCode.UNKNOWN_VALIDATION_ERROR,
            validation_error_detail=error_detail,
            file_size_bytes=1024,
            timestamp=timestamp,
        )

        # When
        with patch("huleedu_service_libs.observability.inject_trace_context"):
            await event_publisher.publish_essay_validation_failed(event_data, sample_correlation_id)

        # Then - Verify OutboxManager was called and extract envelope data
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        envelope = call_args.kwargs["event_data"]

        # Convert envelope to dict to check serialization (envelope has model_dump method)
        envelope_data = envelope.model_dump(mode="json")

        # Verify timestamps are serialized as ISO strings
        assert isinstance(envelope_data["event_timestamp"], str)
        assert isinstance(envelope_data["data"]["timestamp"], str)

        # Verify UUIDs are serialized as strings
        assert isinstance(envelope_data["correlation_id"], str)
        assert envelope_data["correlation_id"] == str(sample_correlation_id)

        # Verify the entire structure is JSON-serializable
        json_str = json.dumps(envelope_data)
        assert json_str  # Should not raise exception

    async def test_all_event_types_use_consistent_patterns(
        self,
        event_publisher: DefaultEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
    ) -> None:
        """Verify all event publishing methods follow consistent patterns."""
        # Given
        timestamp = datetime.now(timezone.utc)

        from common_core.error_enums import FileValidationErrorCode
        from common_core.models.error_models import ErrorDetail

        error_detail = ErrorDetail(
            error_code=FileValidationErrorCode.EMPTY_CONTENT,
            message="File is empty",
            correlation_id=sample_correlation_id,
            timestamp=timestamp,
            service="file-service",
            operation="validate_content",
        )

        # Type annotation for heterogeneous list of event publishing methods
        from typing import Callable

        events_to_test: list[tuple[Callable[..., Any], Any, str, str]] = [
            (
                event_publisher.publish_essay_content_provisioned,
                EssayContentProvisionedV1(
                    entity_id="batch-1",
                    file_upload_id="file-1",
                    original_file_name="test1.pdf",
                    raw_file_storage_id="raw-1",
                    text_storage_id="extracted-1",
                    file_size_bytes=1024,
                    content_md5_hash="hash1",
                    timestamp=timestamp,
                ),
                "file.essay.content.provisioned.v1",
                "file_upload",
            ),
            (
                event_publisher.publish_essay_validation_failed,
                EssayValidationFailedV1(
                    entity_id="batch-2",
                    file_upload_id="file-2",
                    original_file_name="test2.pdf",
                    raw_file_storage_id="raw-2",
                    validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
                    validation_error_detail=error_detail,
                    file_size_bytes=2048,
                    timestamp=timestamp,
                ),
                "file.essay.validation.failed.v1",
                "file_upload",
            ),
            (
                event_publisher.publish_batch_file_added_v1,
                BatchFileAddedV1(
                    batch_id="batch-1",
                    file_upload_id="file-3",
                    filename="test3.pdf",
                    user_id="user-1",
                    timestamp=timestamp,
                ),
                "file.batch.file.added.v1",
                "batch",
            ),
            (
                event_publisher.publish_batch_file_removed_v1,
                BatchFileRemovedV1(
                    batch_id="batch-2",
                    file_upload_id="file-4",
                    filename="test4.pdf",
                    user_id="user-2",
                    timestamp=timestamp,
                ),
                "file.batch.file.removed.v1",
                "batch",
            ),
        ]

        # When
        with patch("huleedu_service_libs.observability.inject_trace_context"):
            for (
                publish_method,
                event_data,
                expected_topic,
                expected_aggregate_type,
            ) in events_to_test:
                await publish_method(event_data, sample_correlation_id)

        # Then - Verify OutboxManager was called 4 times (once for each event)
        assert mock_outbox_manager.publish_to_outbox.call_count == 4

        # Get all call args to verify each call's consistency
        call_args_list = mock_outbox_manager.publish_to_outbox.call_args_list

        for i, (_, event_data, expected_topic, expected_aggregate_type) in enumerate(
            events_to_test
        ):
            call_args = call_args_list[i]

            # All events should follow the same pattern
            assert call_args.kwargs["topic"] == expected_topic
            assert call_args.kwargs["event_type"] == expected_topic
            assert call_args.kwargs["aggregate_type"] == expected_aggregate_type

            # Verify envelope structure
            envelope = call_args.kwargs["event_data"]
            assert envelope.event_type == expected_topic
            assert envelope.source_service == "file-service"
            assert envelope.correlation_id == sample_correlation_id
            assert envelope.data == event_data
            assert hasattr(envelope, "event_timestamp")
            assert hasattr(envelope, "metadata")
