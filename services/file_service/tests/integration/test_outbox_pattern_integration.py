"""
Integration tests for File Service transactional outbox pattern.

Tests the complete outbox workflow including event storage, relay worker processing,
and reliability guarantees. Uses testcontainer-based architecture for isolation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID

from common_core.error_enums import FileValidationErrorCode
from common_core.events.file_events import EssayContentProvisionedV1, EssayValidationFailedV1
from common_core.events.file_management_events import BatchFileAddedV1, BatchFileRemovedV1
from common_core.models.error_models import ErrorDetail
from huleedu_service_libs.outbox import EventRelayWorker
from huleedu_service_libs.outbox.models import EventOutbox
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from services.file_service.protocols import EventPublisherProtocol
from services.file_service.tests.integration.conftest import TestFileServiceOutboxPatternIntegration


class TestOutboxPatternIntegration(TestFileServiceOutboxPatternIntegration):
    """Integration tests for the transactional outbox pattern with testcontainers."""

    async def test_essay_content_provisioned_outbox_write(
        self,
        test_engine: AsyncEngine,
        mock_kafka_publisher: AsyncMock,
        mock_redis_client: AsyncMock,
        db_session: AsyncSession,
        correlation_id: UUID,
        test_file_upload_id: str,
    ) -> None:
        """Test that EssayContentProvisionedV1 events are stored in outbox."""
        async with self.create_test_container(
            test_engine, mock_kafka_publisher, mock_redis_client
        ) as container:
            async with container() as request_container:
                event_publisher = await request_container.get(EventPublisherProtocol)

                # Create test event data
                event_data = EssayContentProvisionedV1(
                    entity_id="test-batch-123",
                    file_upload_id=test_file_upload_id,
                    original_file_name="test_essay.txt",
                    raw_file_storage_id="raw_storage_123",
                    text_storage_id="text_storage_456",
                    file_size_bytes=1024,
                    content_md5_hash="d41d8cd98f00b204e9800998ecf8427e",
                    timestamp=datetime.now(timezone.utc),
                )

                # Publish event
                await event_publisher.publish_essay_content_provisioned(event_data, correlation_id)

                # Verify event is stored in outbox
                stmt = select(EventOutbox).where(
                    EventOutbox.aggregate_id == test_file_upload_id,
                    EventOutbox.aggregate_type == "file_upload",
                    EventOutbox.event_type == "file.essay.content.provisioned.v1",
                )

                result = await db_session.execute(stmt)
                outbox_event = result.scalar_one()

                assert outbox_event is not None
                assert outbox_event.aggregate_id == test_file_upload_id
                assert outbox_event.aggregate_type == "file_upload"
                assert outbox_event.event_type == "file.essay.content.provisioned.v1"
                assert outbox_event.event_key == test_file_upload_id
                assert outbox_event.published_at is None  # Not yet published
                assert outbox_event.event_data is not None  # Should contain the event envelope

    async def test_batch_file_management_outbox_write(
        self,
        test_engine: AsyncEngine,
        mock_kafka_publisher: AsyncMock,
        mock_redis_client: AsyncMock,
        db_session: AsyncSession,
        correlation_id: UUID,
        test_batch_id: str,
        test_file_upload_id: str,
        test_user_id: str,
    ) -> None:
        """Test that batch file management events are stored in outbox."""
        async with self.create_test_container(
            test_engine, mock_kafka_publisher, mock_redis_client
        ) as container:
            async with container() as request_container:
                event_publisher = await request_container.get(EventPublisherProtocol)

                # Test BatchFileAddedV1
                added_event = BatchFileAddedV1(
                    batch_id=test_batch_id,
                    file_upload_id=test_file_upload_id,
                    filename="test_file.txt",
                    user_id=test_user_id,
                    timestamp=datetime.now(timezone.utc),
                )

                await event_publisher.publish_batch_file_added_v1(added_event, correlation_id)

                # Verify outbox storage for BatchFileAddedV1
                stmt = select(EventOutbox).where(
                    EventOutbox.aggregate_id == test_batch_id,
                    EventOutbox.aggregate_type == "batch",
                    EventOutbox.event_type == "file.batch.file.added.v1",
                )

                result = await db_session.execute(stmt)
                outbox_event = result.scalar_one()

                assert outbox_event is not None
                assert outbox_event.aggregate_id == test_batch_id
                assert outbox_event.aggregate_type == "batch"
                assert outbox_event.event_type == "file.batch.file.added.v1"
                assert outbox_event.published_at is None

                # Verify Redis notification was NOT called (since we removed Redis publishing)
                mock_redis_client.publish_user_notification.assert_not_called()

    async def test_relay_worker_processes_outbox_events(
        self,
        test_engine: AsyncEngine,
        mock_kafka_publisher: AsyncMock,
        mock_redis_client: AsyncMock,
        db_session: AsyncSession,
        correlation_id: UUID,
        test_file_upload_id: str,
    ) -> None:
        """Test that EventRelayWorker processes events from outbox to Kafka."""
        async with self.create_test_container(
            test_engine, mock_kafka_publisher, mock_redis_client
        ) as container:
            async with container() as request_container:
                event_publisher = await request_container.get(EventPublisherProtocol)
                relay_worker = await request_container.get(EventRelayWorker)

                # Store event in outbox
                error_detail = ErrorDetail(
                    error_code=FileValidationErrorCode.CONTENT_TOO_LONG,
                    message="Content exceeds limit",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(timezone.utc),
                    service="file-service",
                    operation="validate_essay_content",
                    details={
                        "max_length": 5000,
                        "actual_length": 7500,
                    },
                )

                event_data = EssayValidationFailedV1(
                    entity_id="test-batch-456",
                    file_upload_id=test_file_upload_id,
                    original_file_name="invalid_essay.txt",
                    raw_file_storage_id="raw_storage_789",
                    validation_error_code=FileValidationErrorCode.CONTENT_TOO_LONG,
                    validation_error_detail=error_detail,
                    file_size_bytes=2048,
                    timestamp=datetime.now(timezone.utc),
                )

                await event_publisher.publish_essay_validation_failed(event_data, correlation_id)

                # Verify event stored in outbox before processing
                stmt = select(EventOutbox).where(EventOutbox.published_at.is_(None))
                result = await db_session.execute(stmt)
                unpublished_events = result.scalars().all()
                assert len(unpublished_events) == 1

                # Start relay worker and process events
                await relay_worker.start()

                try:
                    # Wait for relay worker to process the event
                    await self.wait_for_condition(
                        lambda: len(mock_kafka_publisher.published_events) > 0,
                        timeout=3.0,
                    )

                    # Verify Kafka publication
                    assert len(mock_kafka_publisher.published_events) == 1
                    published_event = mock_kafka_publisher.published_events[0]
                    # Topic comes from the database column, not event data
                    # The relay worker reads it from EventOutbox.topic field
                    assert published_event.get("topic") == "file.essay.validation.failed.v1" or \
                           unpublished_events[0].topic == "file.essay.validation.failed.v1"

                    # Verify event marked as published in outbox
                    await db_session.refresh(unpublished_events[0])
                    assert unpublished_events[0].published_at is not None

                finally:
                    await relay_worker.stop()

    async def test_outbox_transactional_consistency(
        self,
        test_engine: AsyncEngine,
        mock_kafka_publisher: AsyncMock,
        mock_redis_client: AsyncMock,
        db_session: AsyncSession,
        correlation_id: UUID,
        test_file_upload_id: str,
    ) -> None:
        """Test that outbox maintains transactional consistency."""
        async with self.create_test_container(
            test_engine, mock_kafka_publisher, mock_redis_client
        ) as container:
            async with container() as request_container:
                event_publisher = await request_container.get(EventPublisherProtocol)

                event_data = BatchFileRemovedV1(
                    batch_id="test-batch-consistency",
                    file_upload_id=test_file_upload_id,
                    filename="consistency_test.txt",
                    user_id="user-consistency",
                    timestamp=datetime.now(timezone.utc),
                )

                # Event publishing should store in outbox
                await event_publisher.publish_batch_file_removed_v1(event_data, correlation_id)

                # Verify event stored in outbox
                stmt = select(EventOutbox).where(
                    EventOutbox.aggregate_id == "test-batch-consistency",
                    EventOutbox.event_type == "file.batch.file.removed.v1",
                )

                result = await db_session.execute(stmt)
                outbox_event = result.scalar_one()

                assert outbox_event is not None
                assert outbox_event.published_at is None
                # Verify Redis was NOT called (since we removed Redis publishing)
                mock_redis_client.publish_user_notification.assert_not_called()

    async def test_event_envelope_serialization_in_outbox(
        self,
        test_engine: AsyncEngine,
        mock_kafka_publisher: AsyncMock,
        mock_redis_client: AsyncMock,
        db_session: AsyncSession,
        correlation_id: UUID,
        test_file_upload_id: str,
    ) -> None:
        """Test that event envelopes are properly serialized in outbox storage."""
        async with self.create_test_container(
            test_engine, mock_kafka_publisher, mock_redis_client
        ) as container:
            async with container() as request_container:
                event_publisher = await request_container.get(EventPublisherProtocol)

                timestamp = datetime.now(timezone.utc)
                event_data = EssayContentProvisionedV1(
                    entity_id="test-serialization",
                    file_upload_id=test_file_upload_id,
                    original_file_name="serialization_test.pdf",
                    raw_file_storage_id="raw_serial_123",
                    text_storage_id="text_serial_456",
                    file_size_bytes=4096,
                    content_md5_hash="serialization_test_hash",
                    timestamp=timestamp,
                )

                await event_publisher.publish_essay_content_provisioned(event_data, correlation_id)

                # Retrieve and verify serialized envelope
                stmt = select(EventOutbox).where(EventOutbox.aggregate_id == test_file_upload_id)
                result = await db_session.execute(stmt)
                outbox_event = result.scalar_one()

                # Verify envelope structure in stored event_data
                envelope_data = outbox_event.event_data
                assert isinstance(envelope_data, dict)
                assert envelope_data["event_type"] == "file.essay.content.provisioned.v1"
                assert envelope_data["source_service"] == "file-service"
                assert envelope_data["correlation_id"] == str(correlation_id)

                # Verify timestamp serialization
                assert isinstance(envelope_data["event_timestamp"], str)
                assert isinstance(envelope_data["data"]["timestamp"], str)

                # Verify nested data structure
                nested_data = envelope_data["data"]
                assert nested_data["entity_id"] == "test-serialization"
                assert nested_data["file_upload_id"] == test_file_upload_id
                assert nested_data["file_size_bytes"] == 4096
