"""
Integration tests for File Service transactional outbox pattern.

Tests the complete outbox workflow including event storage, relay worker processing,
and reliability guarantees during various failure scenarios.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from common_core.events.file_events import EssayContentProvisionedV1, EssayValidationFailedV1
from common_core.events.file_management_events import BatchFileAddedV1, BatchFileRemovedV1
from huleedu_service_libs.outbox import EventRelayWorker
from huleedu_service_libs.outbox.models import EventOutbox
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.file_service.protocols import EventPublisherProtocol


class TestOutboxPatternIntegration:
    """Integration tests for the transactional outbox pattern."""

    async def test_essay_content_provisioned_outbox_write(
        self,
        integration_container: tuple,
        db_session: AsyncSession,
        correlation_id: UUID,
        test_file_upload_id: str,
    ) -> None:
        """Test that EssayContentProvisionedV1 events are stored in outbox."""
        container, _, _ = integration_container

        async with container() as request_container:
            event_publisher = await request_container.get(EventPublisherProtocol)

            # Create test event data
            event_data = EssayContentProvisionedV1(
                batch_id="test-batch-123",
                file_upload_id=test_file_upload_id,
                original_file_name="test_essay.txt",
                raw_file_storage_id="raw_storage_123",
                text_storage_id="text_storage_456",
                file_size_bytes=1024,
                content_md5_hash="d41d8cd98f00b204e9800998ecf8427e",
            )

            # Publish event
            await event_publisher.publish_essay_content_provisioned(event_data, correlation_id)

            # Verify event is stored in outbox
            stmt = select(EventOutbox).where(
                EventOutbox.aggregate_id == test_file_upload_id,
                EventOutbox.aggregate_type == "file_upload",
                EventOutbox.event_type == "huleedu.file.essay.content.provisioned.v1",
            )

            result = await db_session.execute(stmt)
            outbox_event = result.scalar_one()

            assert outbox_event is not None
            assert outbox_event.aggregate_id == test_file_upload_id
            assert outbox_event.aggregate_type == "file_upload"
            assert outbox_event.event_type == "huleedu.file.essay.content.provisioned.v1"
            assert outbox_event.event_key == test_file_upload_id
            assert outbox_event.published_at is None  # Not yet published

            # Basic validation that event was stored correctly
            assert outbox_event.event_data is not None  # Should contain the event envelope

    async def test_batch_file_management_outbox_write(
        self,
        integration_container: tuple,
        db_session: AsyncSession,
        correlation_id: UUID,
        test_batch_id: str,
        test_file_upload_id: str,
        test_user_id: str,
    ) -> None:
        """Test that batch file management events are stored in outbox."""
        container, _, _ = integration_container

        async with container() as request_container:
            event_publisher = await request_container.get(EventPublisherProtocol)

            # Test BatchFileAddedV1
            added_event = BatchFileAddedV1(
                batch_id=test_batch_id,
                file_upload_id=test_file_upload_id,
                filename="test_file.txt",
                user_id=test_user_id,
            )

            await event_publisher.publish_batch_file_added_v1(added_event, correlation_id)

            # Verify outbox storage for BatchFileAddedV1
            stmt = select(EventOutbox).where(
                EventOutbox.aggregate_id == test_batch_id,
                EventOutbox.aggregate_type == "batch",
                EventOutbox.event_type == "huleedu.file.batch.file.added.v1",
            )

            result = await db_session.execute(stmt)
            outbox_event = result.scalar_one()

            assert outbox_event is not None
            assert outbox_event.aggregate_id == test_batch_id
            assert outbox_event.event_key == test_batch_id

            # Test BatchFileRemovedV1
            removed_event = BatchFileRemovedV1(
                batch_id=test_batch_id,
                file_upload_id=test_file_upload_id,
                filename="test_file.txt",
                user_id=test_user_id,
            )

            await event_publisher.publish_batch_file_removed_v1(removed_event, correlation_id)

            # Verify outbox storage for BatchFileRemovedV1
            stmt = select(EventOutbox).where(
                EventOutbox.aggregate_id == test_batch_id,
                EventOutbox.aggregate_type == "batch",
                EventOutbox.event_type == "huleedu.file.batch.file.removed.v1",
            )

            result = await db_session.execute(stmt)
            removed_outbox_event = result.scalar_one()

            assert removed_outbox_event is not None
            assert removed_outbox_event.aggregate_id == test_batch_id

    async def test_relay_worker_processes_outbox_events(
        self,
        integration_container: tuple,
        db_session: AsyncSession,
        mock_kafka_publisher: AsyncMock,
        correlation_id: UUID,
        test_file_upload_id: str,
    ) -> None:
        """Test that EventRelayWorker processes events from outbox and publishes to Kafka."""
        container, _, _ = integration_container

        # Create and store event in outbox BEFORE starting the worker
        async with container() as request_container:
            event_publisher = await request_container.get(EventPublisherProtocol)

            from datetime import UTC, datetime

            from common_core.error_enums import FileValidationErrorCode
            from common_core.models.error_models import ErrorDetail

            error_detail = ErrorDetail(
                error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                message="File content is too short for processing",
                correlation_id=correlation_id,
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate_essay_content",
                details={"min_length": 100, "actual_length": 25},
            )

            event_data = EssayValidationFailedV1(
                batch_id="test-batch-456",
                file_upload_id=test_file_upload_id,
                original_file_name="invalid_essay.txt",
                raw_file_storage_id="raw_storage_456",
                validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                validation_error_detail=error_detail,
                file_size_bytes=128,
            )

            await event_publisher.publish_essay_validation_failed(event_data, correlation_id)

        # Now start the EventRelayWorker - it will process the existing event immediately
        async with container() as request_container:
            worker = await request_container.get(EventRelayWorker)
            worker._kafka_publisher = mock_kafka_publisher
            worker._poll_interval = 0.1
            worker._batch_size = 5

            await worker.start()

            try:
                # Give the worker a moment to process the existing event
                await asyncio.sleep(0.15)  # Just slightly longer than poll interval

                # Verify Kafka publish was called
                mock_kafka_publisher.publish.assert_called()

                # Verify event is marked as published in outbox
                await db_session.commit()  # Refresh to see updates from relay worker

                stmt = select(EventOutbox).where(
                    EventOutbox.aggregate_id == test_file_upload_id,
                    EventOutbox.event_type == "huleedu.file.essay.validation.failed.v1",
                )

                result = await db_session.execute(stmt)
                outbox_event = result.scalar_one()

                assert outbox_event.published_at is not None

                # Verify Kafka message content
                kafka_call_args = mock_kafka_publisher.publish.call_args
                assert kafka_call_args is not None, "Kafka publisher should have been called"
                assert kafka_call_args.kwargs["topic"] == "huleedu.file.essay.validation.failed.v1"

                envelope = kafka_call_args.kwargs["envelope"]
                assert envelope.correlation_id == correlation_id
                assert envelope.data["file_upload_id"] == test_file_upload_id
                assert envelope.data["batch_id"] == "test-batch-456"

            finally:
                await worker.stop()

    async def test_kafka_unavailability_handling(
        self,
        integration_container: tuple,
        db_session: AsyncSession,
        mock_kafka_publisher: AsyncMock,
        correlation_id: UUID,
        test_file_upload_id: str,
    ) -> None:
        """Test that events remain in outbox when Kafka is unavailable."""
        # Configure Kafka to fail
        mock_kafka_publisher.publish.side_effect = Exception("Kafka unavailable")

        container, _, _ = integration_container

        async with container() as request_container:
            event_publisher = await request_container.get(EventPublisherProtocol)
            relay_worker = await request_container.get(EventRelayWorker)
            relay_worker._kafka_publisher = mock_kafka_publisher

            # Store event in outbox
            event_data = EssayContentProvisionedV1(
                batch_id="test-batch-unavailable",
                file_upload_id=test_file_upload_id,
                original_file_name="test_essay.txt",
                raw_file_storage_id="raw_storage_789",
                text_storage_id="text_storage_012",
                file_size_bytes=2048,
                content_md5_hash="098f6bcd4621d373cade4e832627b4f6",
            )

            await event_publisher.publish_essay_content_provisioned(event_data, correlation_id)

            # Start relay worker (it should try and fail)
            await relay_worker.start()
            await asyncio.sleep(0.2)  # Allow processing attempt
            await relay_worker.stop()

            # Verify event remains unprocessed in outbox
            stmt = select(EventOutbox).where(
                EventOutbox.aggregate_id == test_file_upload_id,
                EventOutbox.published_at.is_(None),
            )

            result = await db_session.execute(stmt)
            unprocessed_events = result.scalars().all()

            assert len(unprocessed_events) == 1
            assert unprocessed_events[0].aggregate_id == test_file_upload_id

            # Now restore Kafka and verify processing succeeds
            mock_kafka_publisher.publish.side_effect = None
            mock_kafka_publisher.publish.return_value = None

            await relay_worker.start()
            await asyncio.sleep(0.2)  # Allow successful processing
            await relay_worker.stop()

            # Refresh session to see updates from EventRelayWorker
            # The EventRelayWorker uses its own sessions and commits changes
            # We need to refresh our session to see those committed changes
            await db_session.rollback()  # Clear any pending changes
            db_session.expire_all()  # Invalidate cached objects to force refresh

            # CRITICAL TEST: Verify event is now processed after Kafka recovery
            # EventRelayWorker should have retried and successfully published the event
            stmt = select(EventOutbox).where(
                EventOutbox.aggregate_id == test_file_upload_id,
            )

            result = await db_session.execute(stmt)
            processed_event = result.scalar_one()

            # THIS MUST PASS for proper outbox resilience guarantees
            assert processed_event.published_at is not None, (
                "Event should be published after Kafka recovery"
            )

    async def test_transaction_rollback_scenario(
        self,
        integration_container: tuple,
        db_session: AsyncSession,
        correlation_id: UUID,
        test_file_upload_id: str,
    ) -> None:
        """Test that outbox events are rolled back with failed transactions."""
        container, _, _ = integration_container

        async with container() as request_container:
            from huleedu_service_libs.outbox import OutboxRepositoryProtocol

            outbox_repository = await request_container.get(OutboxRepositoryProtocol)

            # Test transaction rollback behavior with session injection
            # Solution: Use session injection to ensure outbox participates in transaction

            # Start a transaction that will be rolled back
            try:
                async with db_session.begin():
                    # Add event to outbox within transaction using shared session
                    # This ensures the outbox write participates in the same transaction
                    await outbox_repository.add_event(
                        aggregate_id=test_file_upload_id,
                        aggregate_type="file_upload",
                        event_type="test.rollback.event",
                        event_data={"test": "data"},
                        topic="test.topic",
                        event_key=test_file_upload_id,
                        session=db_session,  # Use shared session for transaction
                    )

                    # Verify event exists within transaction
                    stmt = select(EventOutbox).where(
                        EventOutbox.aggregate_id == test_file_upload_id,
                        EventOutbox.event_type == "test.rollback.event",
                    )

                    result = await db_session.execute(stmt)
                    event_in_transaction = result.scalar_one_or_none()
                    assert event_in_transaction is not None

                    # Force rollback by raising exception
                    raise Exception("Simulated transaction failure")
            except Exception as e:
                # Expected exception to trigger rollback
                assert str(e) == "Simulated transaction failure"

            # After rollback, verify event is not in outbox
            # The session injection ensures proper transactional rollback behavior
            await db_session.rollback()

            stmt = select(EventOutbox).where(
                EventOutbox.aggregate_id == test_file_upload_id,
                EventOutbox.event_type == "test.rollback.event",
            )

            result = await db_session.execute(stmt)
            rolled_back_event = result.scalar_one_or_none()

            # With session injection, this should now pass
            assert rolled_back_event is None, "Event should have been rolled back with transaction"

    @pytest.mark.no_prometheus_clear
    async def test_outbox_with_metrics_enabled(
        self,
        integration_container: tuple,
        mock_kafka_publisher: AsyncMock,
        correlation_id: UUID,
        test_file_upload_id: str,
    ) -> None:
        """Test that outbox operations work correctly with metrics enabled."""
        container, _, _ = integration_container

        async with container() as request_container:
            event_publisher = await request_container.get(EventPublisherProtocol)

            # Create our own event relay worker for this test
            relay_worker = await request_container.get(EventRelayWorker)
            relay_worker._kafka_publisher = mock_kafka_publisher
            relay_worker._poll_interval = 0.1  # Fast polling for tests

            # Create and publish event
            event_data = EssayContentProvisionedV1(
                batch_id="test-batch-metrics",
                file_upload_id=test_file_upload_id,
                original_file_name="metrics_test.txt",
                raw_file_storage_id="raw_storage_metrics",
                text_storage_id="text_storage_metrics",
                file_size_bytes=512,
            )

            # Store event in outbox
            await event_publisher.publish_essay_content_provisioned(event_data, correlation_id)

            # Process event with relay worker
            await relay_worker.start()
            await asyncio.sleep(0.2)  # Allow processing
            await relay_worker.stop()

            # Verify end-to-end flow completed successfully
            mock_kafka_publisher.publish.assert_called()

            # Basic validation that metrics are being collected (without checking specific values)
            # Detailed metrics testing belongs in unit tests
            assert relay_worker.metrics is not None

    async def test_duplicate_event_idempotency(
        self,
        integration_container: tuple,
        db_session: AsyncSession,
        correlation_id: UUID,
        test_file_upload_id: str,
    ) -> None:
        """Test that duplicate events with same correlation_id are handled correctly."""
        container, _, _ = integration_container

        async with container() as request_container:
            event_publisher = await request_container.get(EventPublisherProtocol)

            event_data = EssayContentProvisionedV1(
                batch_id="test-batch-duplicate",
                file_upload_id=test_file_upload_id,
                original_file_name="duplicate_test.txt",
                raw_file_storage_id="raw_storage_duplicate",
                text_storage_id="text_storage_duplicate",
                file_size_bytes=256,
                content_md5_hash="e99a18c428cb38d5f260853678922e03",
            )

            # Publish same event twice with same correlation_id
            await event_publisher.publish_essay_content_provisioned(event_data, correlation_id)
            await event_publisher.publish_essay_content_provisioned(event_data, correlation_id)

            # Check how many events are stored
            stmt = select(EventOutbox).where(
                EventOutbox.aggregate_id == test_file_upload_id,
                EventOutbox.event_type == "huleedu.file.essay.content.provisioned.v1",
            )

            result = await db_session.execute(stmt)
            events = result.scalars().all()

            # Should have 2 events (outbox doesn't deduplicate, that's handled at consumer level)
            assert len(events) == 2

            # Both events should have the same correlation_id in their data
            for event in events:
                event_data = event.event_data  # SQLAlchemy auto-deserializes JSON
                assert event_data["correlation_id"] == str(correlation_id)
