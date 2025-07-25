"""
Integration tests for the Transactional Outbox Pattern.

These tests validate the complete flow from business operation through
event storage in the outbox to final delivery to Kafka. They ensure
the pattern maintains consistency and handles various failure scenarios.

Note: These are integration tests, not true end-to-end tests, as they
use TestContainers for infrastructure but test isolated components.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from aiokafka import AIOKafkaConsumer
from common_core.domain_enums import CourseCode
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.events.file_events import EssayContentProvisionedV1
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.redis_client import RedisClient
from sqlalchemy import text as sa_text
from testcontainers.kafka import KafkaContainer
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

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
from services.essay_lifecycle_service.implementations.essay_repository_postgres_impl import (
    PostgreSQLEssayRepository,
)
from services.essay_lifecycle_service.implementations.event_publisher import DefaultEventPublisher
from services.essay_lifecycle_service.implementations.event_relay_worker import EventRelayWorker
from services.essay_lifecycle_service.implementations.outbox_repository_impl import (
    PostgreSQLOutboxRepository,
)
from services.essay_lifecycle_service.implementations.redis_batch_coordinator import (
    RedisBatchCoordinator,
)

logger = create_service_logger("test.outbox_integration")


class KafkaMessageCapture:
    """Captures messages from Kafka topics for test verification."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self._consumer: AIOKafkaConsumer | None = None
        self._consume_task: asyncio.Task | None = None

    async def start_consuming(self, bootstrap_servers: str, topics: list[str]) -> None:
        """Start consuming from specified topics."""
        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap_servers,
            group_id=f"test-e2e-{uuid4().hex[:8]}",
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )

        await self._consumer.start()
        self._consume_task = asyncio.create_task(self._consume_loop())
        logger.info(f"Started consuming from topics: {topics}")

    async def _consume_loop(self) -> None:
        """Consume messages in a loop."""
        if not self._consumer:
            return

        try:
            async for msg in self._consumer:
                try:
                    value = json.loads(msg.value.decode("utf-8"))
                    self.messages.append(
                        {
                            "topic": msg.topic,
                            "key": msg.key.decode("utf-8") if msg.key else None,
                            "value": value,
                            "offset": msg.offset,
                            "timestamp": msg.timestamp,
                        }
                    )
                    logger.info(
                        "Captured Kafka message",
                        extra={
                            "topic": msg.topic,
                            "event_type": value.get("event_type"),
                            "offset": msg.offset,
                        },
                    )
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        """Stop consuming messages."""
        if self._consume_task:
            self._consume_task.cancel()
            try:
                await self._consume_task
            except asyncio.CancelledError:
                pass

        if self._consumer:
            await self._consumer.stop()

    def find_events_by_type(self, event_type: str) -> list[dict[str, Any]]:
        """Find all messages with a specific event type."""
        return [msg for msg in self.messages if msg["value"].get("event_type") == event_type]


@pytest.mark.integration
@pytest.mark.docker
@pytest.mark.asyncio
class TestOutboxPatternIntegration:
    """Integration tests for the Transactional Outbox Pattern."""

    @pytest.fixture
    async def test_infrastructure(self) -> AsyncIterator[dict[str, Any]]:
        """Set up complete test infrastructure with all containers."""
        # Start containers
        postgres = PostgresContainer("postgres:15")
        redis = RedisContainer("redis:7-alpine")
        kafka = KafkaContainer("confluentinc/cp-kafka:7.4.0")  # Use stable 7.4.0 version

        with postgres, redis, kafka:
            # Properly wait for Kafka to be ready
            kafka_url = kafka.get_bootstrap_server()

            # Get other connection strings
            db_url = (
                f"postgresql+asyncpg://{postgres.username}:{postgres.password}@"
                f"{postgres.get_container_host_ip()}:{postgres.get_exposed_port(5432)}/{postgres.dbname}"
            )
            redis_url = f"redis://{postgres.get_container_host_ip()}:{redis.get_exposed_port(6379)}"

            # Create a custom settings object with the test database URL
            test_settings = Settings(
                DATABASE_URL=db_url,
                REDIS_URL=redis_url,
                KAFKA_BOOTSTRAP_SERVERS=kafka_url,
                # Use test-optimized settings
                OUTBOX_POLL_INTERVAL_SECONDS=0.5,  # Fast polling for tests
                OUTBOX_BATCH_SIZE=10,
                OUTBOX_MAX_RETRIES=3,
                OUTBOX_ERROR_RETRY_INTERVAL_SECONDS=0.5,
            )

            # Initialize essay repository first (it creates its own engine)
            essay_repo = PostgreSQLEssayRepository(test_settings)
            # Initialize the repository schema and run migrations
            await essay_repo.initialize_db_schema()
            await essay_repo.run_migrations()

            # Use the engine from the essay repository for all other components
            # This ensures all components share the same database connection pool
            engine = essay_repo.engine

            # Add a small delay to ensure all services are fully ready
            await asyncio.sleep(2)

            # Initialize Redis
            redis_client = RedisClient(client_id="test-e2e", redis_url=redis_url)
            await redis_client.start()

            # Initialize Kafka
            kafka_bus = KafkaBus(
                client_id="test-e2e",
                bootstrap_servers=kafka_url,
            )
            await kafka_bus.start()

            # Create outbox repository using shared engine
            outbox_repo = PostgreSQLOutboxRepository(engine)

            # Create batch tracking components using shared engine
            redis_coordinator = RedisBatchCoordinator(redis_client, test_settings)
            persistence = BatchTrackerPersistence(engine)
            batch_tracker = DefaultBatchEssayTracker(persistence, redis_coordinator)
            await batch_tracker.initialize_from_database()

            # Create event publisher with outbox
            event_publisher = DefaultEventPublisher(
                kafka_bus=kafka_bus,
                settings=test_settings,
                redis_client=redis_client,
                batch_tracker=batch_tracker,
                outbox_repository=outbox_repo,
            )

            # Create handler
            handler = DefaultBatchCoordinationHandler(
                batch_tracker=batch_tracker,
                repository=essay_repo,
                event_publisher=event_publisher,
            )

            # Create relay worker
            relay_worker = EventRelayWorker(
                kafka_bus=kafka_bus,
                outbox_repository=outbox_repo,
                settings=test_settings,
            )

            # Create Kafka message capture
            capture = KafkaMessageCapture()

            yield {
                "settings": test_settings,
                "handler": handler,
                "outbox_repo": outbox_repo,
                "relay_worker": relay_worker,
                "capture": capture,
                "engine": engine,
                "kafka_url": kafka_url,
                "kafka_bus": kafka_bus,
                "redis_client": redis_client,
            }

            # Cleanup
            await kafka_bus.stop()
            await redis_client.stop()
            await engine.dispose()

    async def test_happy_path_business_operation_to_kafka_delivery(
        self, test_infrastructure: dict[str, Any]
    ) -> None:
        """Test complete flow: business operation → outbox → Kafka delivery."""
        # Arrange
        handler = test_infrastructure["handler"]
        outbox_repo = test_infrastructure["outbox_repo"]
        relay_worker = test_infrastructure["relay_worker"]
        capture = test_infrastructure["capture"]
        kafka_url = test_infrastructure["kafka_url"]
        engine = test_infrastructure["engine"]

        # Start Kafka consumer
        await capture.start_consuming(
            bootstrap_servers=kafka_url,
            topics=["huleedu.els.essay.slot.assigned.v1"],
        )

        # Start relay worker
        await relay_worker.start()

        try:
            # Execute business operation
            batch_id = str(uuid4())
            essay_id = str(uuid4())
            correlation_id = uuid4()

            # Register batch
            batch_event = BatchEssaysRegistered(
                batch_id=batch_id,
                course_code=CourseCode.ENG5,
                essay_instructions="E2E test essay",
                essay_ids=[essay_id],
                expected_essay_count=1,
                user_id="e2e_test_user",
                metadata=SystemProcessingMetadata(
                    entity=EntityReference(
                        entity_id=batch_id,
                        entity_type="batch",
                        parent_id=None,
                    ),
                    timestamp=datetime.now(UTC),
                ),
            )

            success = await handler.handle_batch_essays_registered(batch_event, correlation_id)
            assert success, "Batch registration should succeed"

            # Give the system a moment to ensure database writes are committed
            await asyncio.sleep(0.5)

            # Verify batch was created in database before proceeding
            async with engine.begin() as conn:
                result = await conn.execute(
                    sa_text("SELECT COUNT(*) FROM batch_essay_trackers WHERE batch_id = :batch_id"),
                    {"batch_id": batch_id},
                )
                count = result.scalar()
                assert count == 1, f"Batch not found in database after registration: {count}"

                # Also check essay_states
                result = await conn.execute(
                    sa_text("SELECT COUNT(*) FROM essay_states WHERE batch_id = :batch_id"),
                    {"batch_id": batch_id},
                )
                essay_count = result.scalar()
                logger.info(f"Found {essay_count} essay states for batch {batch_id}")

            # Provision content (triggers outbox event)
            file_upload_id = f"upload_{uuid4().hex[:8]}"
            text_storage_id = f"text_{uuid4().hex[:8]}"

            content_event = EssayContentProvisionedV1(
                batch_id=batch_id,
                file_upload_id=file_upload_id,
                original_file_name="test.txt",
                raw_file_storage_id=f"raw_{uuid4().hex[:8]}",
                text_storage_id=text_storage_id,
                file_size_bytes=1024,
                content_md5_hash="abc123",
                correlation_id=correlation_id,
            )

            success = await handler.handle_essay_content_provisioned(content_event, correlation_id)
            assert success, "Content provisioning should succeed"

            # Wait for relay worker to process
            await asyncio.sleep(3.0)

            # Verify outbox is empty (event was published)
            unpublished = await outbox_repo.get_unpublished_events(limit=10)
            assert len(unpublished) == 0, (
                f"All events should be published, found {len(unpublished)}"
            )

            # Verify Kafka received the message
            slot_events = capture.find_events_by_type("huleedu.els.essay.slot.assigned.v1")
            assert len(slot_events) > 0, "Essay slot assigned event should be in Kafka"

            # Verify event content
            event = slot_events[0]["value"]
            assert event["data"]["batch_id"] == batch_id
            assert event["data"]["file_upload_id"] == file_upload_id
            assert event["data"]["text_storage_id"] == text_storage_id

        finally:
            await relay_worker.stop()
            await capture.stop()

    async def test_kafka_failure_recovery(self, test_infrastructure: dict[str, Any]) -> None:
        """Test that events are retried when Kafka is temporarily unavailable."""
        # Arrange
        handler = test_infrastructure["handler"]
        outbox_repo = test_infrastructure["outbox_repo"]
        relay_worker = test_infrastructure["relay_worker"]
        kafka_bus = test_infrastructure["kafka_bus"]

        # Save original publish method
        original_publish = kafka_bus.publish
        publish_attempts = []

        # Mock Kafka to fail initially
        async def failing_publish(topic: str, envelope: Any, key: str | None = None) -> None:
            publish_attempts.append(topic)
            if len(publish_attempts) <= 2:  # Fail first 2 attempts
                raise Exception("Kafka temporarily unavailable")
            # Succeed on 3rd attempt
            await original_publish(topic, envelope, key)

        kafka_bus.publish = failing_publish

        # Start relay worker
        await relay_worker.start()

        try:
            # Execute business operation
            batch_id = str(uuid4())
            correlation_id = uuid4()

            batch_event = BatchEssaysRegistered(
                batch_id=batch_id,
                course_code=CourseCode.ENG5,
                essay_instructions="Failure recovery test",
                essay_ids=[str(uuid4())],
                expected_essay_count=1,
                user_id="test_user",
                metadata=SystemProcessingMetadata(
                    entity=EntityReference(
                        entity_id=batch_id,
                        entity_type="batch",
                        parent_id=None,
                    ),
                    timestamp=datetime.now(UTC),
                ),
            )

            await handler.handle_batch_essays_registered(batch_event, correlation_id)

            content_event = EssayContentProvisionedV1(
                batch_id=batch_id,
                file_upload_id=f"upload_{uuid4().hex[:8]}",
                original_file_name="test.txt",
                raw_file_storage_id=f"raw_{uuid4().hex[:8]}",
                text_storage_id=f"text_{uuid4().hex[:8]}",
                file_size_bytes=1024,
                content_md5_hash="xyz789",
                correlation_id=correlation_id,
            )

            success = await handler.handle_essay_content_provisioned(content_event, correlation_id)
            assert success, "Business operation should succeed even with Kafka issues"

            # Wait for retries
            await asyncio.sleep(5.0)

            # Verify event was retried and eventually published
            assert len(publish_attempts) >= 3, f"Should retry, got {len(publish_attempts)} attempts"

            # Verify event marked as published
            unpublished = await outbox_repo.get_unpublished_events(limit=10)
            assert len(unpublished) == 0, "Event should be published after recovery"

        finally:
            kafka_bus.publish = original_publish  # Restore
            await relay_worker.stop()

    async def test_transaction_rollback_no_events_published(
        self, test_infrastructure: dict[str, Any]
    ) -> None:
        """Test that events are not published when business transaction fails."""
        # Arrange
        handler = test_infrastructure["handler"]
        outbox_repo = test_infrastructure["outbox_repo"]
        relay_worker = test_infrastructure["relay_worker"]

        # Start relay worker
        await relay_worker.start()

        try:
            # Create an invalid batch event (empty essay list)
            batch_id = str(uuid4())
            correlation_id = uuid4()

            batch_event = BatchEssaysRegistered(
                batch_id=batch_id,
                course_code=CourseCode.ENG5,
                essay_instructions="Transaction rollback test",
                essay_ids=[],  # Empty - will cause validation failure
                expected_essay_count=0,
                user_id="test_user",
                metadata=SystemProcessingMetadata(
                    entity=EntityReference(
                        entity_id=batch_id,
                        entity_type="batch",
                        parent_id=None,
                    ),
                    timestamp=datetime.now(UTC),
                ),
            )

            # This should fail - handler raises exception for invalid input
            from huleedu_service_libs.error_handling import HuleEduError

            with pytest.raises(HuleEduError) as exc_info:
                await handler.handle_batch_essays_registered(batch_event, correlation_id)

            # Verify it's a processing error
            assert exc_info.value.error_detail.error_code == "PROCESSING_ERROR"

            # Wait for any potential processing
            await asyncio.sleep(1.0)

            # Verify no events in outbox
            unpublished = await outbox_repo.get_unpublished_events(limit=10)
            assert len(unpublished) == 0, "No events should be in outbox after failed transaction"

        finally:
            await relay_worker.stop()

    async def test_concurrent_relay_workers_no_duplicates(
        self, test_infrastructure: dict[str, Any]
    ) -> None:
        """Test that multiple relay workers don't cause duplicate deliveries."""
        # Arrange
        handler = test_infrastructure["handler"]
        outbox_repo = test_infrastructure["outbox_repo"]
        kafka_bus = test_infrastructure["kafka_bus"]
        settings = test_infrastructure["settings"]
        capture = test_infrastructure["capture"]
        kafka_url = test_infrastructure["kafka_url"]

        # Create two relay workers
        relay_worker1 = test_infrastructure["relay_worker"]
        relay_worker2 = EventRelayWorker(
            kafka_bus=kafka_bus,
            outbox_repository=outbox_repo,
            settings=settings,
        )

        # Start Kafka consumer
        await capture.start_consuming(
            bootstrap_servers=kafka_url,
            topics=["huleedu.els.essay.slot.assigned.v1"],
        )

        # Execute business operation BEFORE starting workers
        batch_id = str(uuid4())
        correlation_id = uuid4()
        file_upload_id = f"upload_concurrent_{uuid4().hex[:8]}"

        batch_event = BatchEssaysRegistered(
            batch_id=batch_id,
            course_code=CourseCode.ENG5,
            essay_instructions="Concurrent workers test",
            essay_ids=[str(uuid4())],
            expected_essay_count=1,
            user_id="test_user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_id=batch_id,
                    entity_type="batch",
                    parent_id=None,
                ),
                timestamp=datetime.now(UTC),
            ),
        )

        await handler.handle_batch_essays_registered(batch_event, correlation_id)

        content_event = EssayContentProvisionedV1(
            batch_id=batch_id,
            file_upload_id=file_upload_id,
            original_file_name="concurrent.txt",
            raw_file_storage_id=f"raw_{uuid4().hex[:8]}",
            text_storage_id=f"text_{uuid4().hex[:8]}",
            file_size_bytes=2048,
            content_md5_hash="concurrent123",
            correlation_id=correlation_id,
        )

        await handler.handle_essay_content_provisioned(content_event, correlation_id)

        # Verify event is in outbox before starting workers
        unpublished = await outbox_repo.get_unpublished_events(limit=10)
        assert len(unpublished) == 1, "Event should be in outbox"

        # Now start BOTH workers concurrently
        await relay_worker1.start()
        await relay_worker2.start()

        try:
            # Wait for processing
            await asyncio.sleep(3.0)

            # Verify no duplicates in Kafka
            slot_events = capture.find_events_by_type("huleedu.els.essay.slot.assigned.v1")
            matching_events = [
                e for e in slot_events if e["value"]["data"]["file_upload_id"] == file_upload_id
            ]

            assert len(matching_events) == 1, (
                f"Should have exactly 1 event, got {len(matching_events)}"
            )

            # Verify outbox is empty
            unpublished = await outbox_repo.get_unpublished_events(limit=10)
            assert len(unpublished) == 0, "Event should be published exactly once"

        finally:
            await relay_worker1.stop()
            await relay_worker2.stop()
            await capture.stop()
