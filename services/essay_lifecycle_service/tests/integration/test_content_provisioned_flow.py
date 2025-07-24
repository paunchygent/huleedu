"""
Integration test for EssayContentProvisionedV1 event handling flow.

This test validates the critical File Service → ELS event flow, focusing on:
- Atomic Redis slot assignment with proper transaction handling
- Event publishing patterns and reliability
- Error scenarios and transaction rollbacks
- Idempotency of content provisioning

Uses testcontainers for isolated testing environment.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.domain_enums import ContentType, CourseCode
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.events.file_events import EssayContentProvisionedV1
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from common_core.status_enums import EssayStatus
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.redis_client import RedisClient
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
from services.essay_lifecycle_service.implementations.redis_batch_coordinator import (
    RedisBatchCoordinator,
)

logger = create_service_logger("test.content_provisioned_flow")


@pytest.mark.integration
@pytest.mark.asyncio
class TestContentProvisionedFlow:
    """Test the File Service → ELS event handling flow."""

    @pytest.fixture
    async def test_infrastructure(self) -> AsyncIterator[dict[str, Any]]:
        """Set up complete test infrastructure with containers."""
        # Start containers
        redis_container = RedisContainer("redis:7-alpine")
        postgres_container = PostgresContainer("postgres:15")

        with redis_container as redis, postgres_container as pg:
            # Connection strings
            redis_url = f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}"
            db_url = (
                f"postgresql+asyncpg://{pg.username}:{pg.password}@"
                f"{pg.get_container_host_ip()}:{pg.get_exposed_port(5432)}/{pg.dbname}"
            )

            # Configure environment
            import os

            os.environ["ESSAY_LIFECYCLE_SERVICE_DATABASE_URL"] = db_url
            os.environ["ESSAY_LIFECYCLE_SERVICE_REDIS_URL"] = redis_url

            settings = Settings()

            # Initialize components
            redis_client = RedisClient(client_id="test-els", redis_url=redis_url)
            await redis_client.start()

            redis_coordinator = RedisBatchCoordinator(redis_client, settings)

            repository = PostgreSQLEssayRepository(settings)
            await repository.initialize_db_schema()
            await repository.run_migrations()

            persistence = BatchTrackerPersistence(repository.engine)
            batch_tracker = DefaultBatchEssayTracker(persistence, redis_coordinator)
            await batch_tracker.initialize_from_database()

            # Mock Kafka bus - we'll spy on the events published
            mock_kafka_bus = AsyncMock()
            published_events = []

            async def capture_event(topic: str, envelope: Any, key: str | None = None) -> None:
                # Serialize envelope to match actual Kafka publishing
                import json

                serialized = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
                published_events.append(
                    {"topic": topic, "envelope": envelope, "serialized": serialized, "key": key}
                )

            mock_kafka_bus.publish.side_effect = capture_event

            event_publisher = DefaultEventPublisher(
                kafka_bus=mock_kafka_bus,
                settings=settings,
                redis_client=redis_client,
                batch_tracker=batch_tracker,
            )

            handler = DefaultBatchCoordinationHandler(
                batch_tracker=batch_tracker,
                repository=repository,
                event_publisher=event_publisher,
            )

            yield {
                "handler": handler,
                "repository": repository,
                "batch_tracker": batch_tracker,
                "redis_coordinator": redis_coordinator,
                "redis_client": redis_client,
                "event_publisher": event_publisher,
                "published_events": published_events,
                "mock_kafka_bus": mock_kafka_bus,
            }

            # Cleanup
            await redis_client.stop()
            await repository.engine.dispose()

    async def test_content_provisioned_atomic_slot_assignment(
        self, test_infrastructure: dict[str, Any]
    ) -> None:
        """Test atomic slot assignment with proper Redis transactions."""
        handler = test_infrastructure["handler"]
        repository = test_infrastructure["repository"]
        published_events = test_infrastructure["published_events"]

        # Setup: Register batch
        batch_id = str(uuid4())
        essay_ids = [str(uuid4()) for _ in range(3)]
        correlation_id = uuid4()

        batch_event = BatchEssaysRegistered(
            batch_id=batch_id,
            course_code=CourseCode.ENG5,
            essay_instructions="Test atomic assignment",
            essay_ids=essay_ids,
            expected_essay_count=len(essay_ids),
            user_id="test_user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_id=batch_id,
                    entity_type="batch",
                    parent_id=None,
                ),
                timestamp=datetime.now(UTC),
                processing_stage=None,
            ),
        )

        await handler.handle_batch_essays_registered(batch_event, correlation_id)

        # Test: Handle content provisioned event
        file_upload_id = f"upload_{uuid4().hex[:8]}"
        text_storage_id = f"text_{uuid4().hex[:8]}"

        content_event = EssayContentProvisionedV1(
            batch_id=batch_id,
            file_upload_id=file_upload_id,
            original_file_name="test_atomic.txt",
            raw_file_storage_id=f"raw_{uuid4().hex[:8]}",
            text_storage_id=text_storage_id,
            file_size_bytes=2048,
            content_md5_hash="def789",
            correlation_id=correlation_id,
        )

        success = await handler.handle_essay_content_provisioned(content_event, correlation_id)
        assert success, "Content provisioning should succeed"

        # Verify database state
        essays = await repository.list_essays_by_batch(batch_id)
        assigned_essay = None
        for essay in essays:
            if ContentType.ORIGINAL_ESSAY in essay.storage_references:
                assigned_essay = essay
                break

        assert assigned_essay is not None, "One essay should have content assigned"
        assert assigned_essay.storage_references[ContentType.ORIGINAL_ESSAY] == text_storage_id
        assert assigned_essay.current_status == EssayStatus.READY_FOR_PROCESSING

        # Verify event published
        assert len(published_events) > 0, "Should publish events"

        # Find the EssaySlotAssignedV1 event
        slot_assigned_event = None
        for event in published_events:
            if "essay.slot.assigned" in event["topic"]:
                envelope = event["envelope"]
                if "essay.slot.assigned" in envelope.event_type:
                    slot_assigned_event = envelope
                    break

        assert slot_assigned_event is not None, "EssaySlotAssignedV1 should be published"
        assert slot_assigned_event.data.file_upload_id == file_upload_id
        assert slot_assigned_event.data.essay_id == str(assigned_essay.essay_id)
        assert slot_assigned_event.data.text_storage_id == text_storage_id

    async def test_concurrent_content_provisioning(
        self, test_infrastructure: dict[str, Any]
    ) -> None:
        """Test multiple concurrent content provisioning requests."""
        handler = test_infrastructure["handler"]
        repository = test_infrastructure["repository"]
        redis_coordinator = test_infrastructure["redis_coordinator"]

        # Setup: Register batch with 5 essays
        batch_id = str(uuid4())
        essay_ids = [str(uuid4()) for _ in range(5)]
        correlation_id = uuid4()

        batch_event = BatchEssaysRegistered(
            batch_id=batch_id,
            course_code=CourseCode.ENG5,
            essay_instructions="Concurrent test",
            essay_ids=essay_ids,
            expected_essay_count=len(essay_ids),
            user_id="test_user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_id=batch_id,
                    entity_type="batch",
                    parent_id=None,
                ),
                timestamp=datetime.now(UTC),
                processing_stage=None,
            ),
        )

        await handler.handle_batch_essays_registered(batch_event, correlation_id)

        # Test: Concurrent content provisioning
        async def provision_content(index: int) -> tuple[bool, str]:
            """Provision content for a single file."""
            file_upload_id = f"upload_concurrent_{index}_{uuid4().hex[:8]}"
            content_event = EssayContentProvisionedV1(
                batch_id=batch_id,
                file_upload_id=file_upload_id,
                original_file_name=f"concurrent_{index}.txt",
                raw_file_storage_id=f"raw_{index}_{uuid4().hex[:8]}",
                text_storage_id=f"text_{index}_{uuid4().hex[:8]}",
                file_size_bytes=1024 * (index + 1),
                content_md5_hash=f"hash_{index}",
                correlation_id=correlation_id,
            )

            success = await handler.handle_essay_content_provisioned(content_event, correlation_id)
            return success, file_upload_id

        # Launch concurrent provisioning
        results = await asyncio.gather(
            *[provision_content(i) for i in range(5)],
            return_exceptions=True,
        )

        # Verify results
        successful_provisions = []
        for result in results:
            if (
                not isinstance(result, BaseException)
                and isinstance(result, tuple)
                and len(result) == 2
            ):
                success, fid = result
                if success:
                    successful_provisions.append((success, fid))
        assert len(successful_provisions) == 5, "All provisions should succeed"

        # Verify no duplicate assignments
        essays = await repository.list_essays_by_batch(batch_id)
        assigned_essays = [e for e in essays if ContentType.ORIGINAL_ESSAY in e.storage_references]
        assert len(assigned_essays) == 5, "All essays should have content"

        # Verify Redis state consistency
        remaining_slots = await redis_coordinator.get_available_slot_count(batch_id)
        assert remaining_slots == 0, "All slots should be consumed"

    async def test_idempotent_content_provisioning(
        self, test_infrastructure: dict[str, Any]
    ) -> None:
        """Test idempotency of content provisioning."""
        handler = test_infrastructure["handler"]
        repository = test_infrastructure["repository"]
        published_events = test_infrastructure["published_events"]

        # Setup: Register batch
        batch_id = str(uuid4())
        essay_ids = [str(uuid4()) for _ in range(2)]
        correlation_id = uuid4()

        batch_event = BatchEssaysRegistered(
            batch_id=batch_id,
            course_code=CourseCode.ENG5,
            essay_instructions="Idempotency test",
            essay_ids=essay_ids,
            expected_essay_count=len(essay_ids),
            user_id="test_user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_id=batch_id,
                    entity_type="batch",
                    parent_id=None,
                ),
                timestamp=datetime.now(UTC),
                processing_stage=None,
            ),
        )

        await handler.handle_batch_essays_registered(batch_event, correlation_id)

        # Test: Provision content twice with same text_storage_id
        file_upload_id = f"upload_idempotent_{uuid4().hex[:8]}"
        text_storage_id = f"text_idempotent_{uuid4().hex[:8]}"

        content_event = EssayContentProvisionedV1(
            batch_id=batch_id,
            file_upload_id=file_upload_id,
            original_file_name="idempotent.txt",
            raw_file_storage_id=f"raw_{uuid4().hex[:8]}",
            text_storage_id=text_storage_id,
            file_size_bytes=1536,
            content_md5_hash="idempotent123",
            correlation_id=correlation_id,
        )

        # Clear published events
        published_events.clear()

        # First provision
        success1 = await handler.handle_essay_content_provisioned(content_event, correlation_id)
        assert success1, "First provision should succeed"
        events_after_first = len(published_events)

        # Second provision (idempotent)
        success2 = await handler.handle_essay_content_provisioned(content_event, correlation_id)
        assert success2, "Second provision should succeed (idempotent)"

        # Should publish same number of events (idempotent)
        assert len(published_events) == events_after_first * 2, (
            "Should publish events for both calls"
        )

        # Verify only one essay has content
        essays = await repository.list_essays_by_batch(batch_id)
        assigned_count = sum(
            1 for e in essays if ContentType.ORIGINAL_ESSAY in e.storage_references
        )
        assert assigned_count == 1, "Only one essay should have content assigned"

    async def test_event_publishing_failure_handling(
        self, test_infrastructure: dict[str, Any]
    ) -> None:
        """Test behavior when event publishing fails."""
        handler = test_infrastructure["handler"]
        mock_kafka_bus = test_infrastructure["mock_kafka_bus"]

        # Setup: Register batch
        batch_id = str(uuid4())
        essay_ids = [str(uuid4()) for _ in range(2)]
        correlation_id = uuid4()

        batch_event = BatchEssaysRegistered(
            batch_id=batch_id,
            course_code=CourseCode.ENG5,
            essay_instructions="Publishing failure test",
            essay_ids=essay_ids,
            expected_essay_count=len(essay_ids),
            user_id="test_user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_id=batch_id,
                    entity_type="batch",
                    parent_id=None,
                ),
                timestamp=datetime.now(UTC),
                processing_stage=None,
            ),
        )

        await handler.handle_batch_essays_registered(batch_event, correlation_id)

        # Configure Kafka to fail
        mock_kafka_bus.publish.side_effect = Exception("Kafka unavailable")

        # Test: Try to provision content
        content_event = EssayContentProvisionedV1(
            batch_id=batch_id,
            file_upload_id=f"upload_fail_{uuid4().hex[:8]}",
            original_file_name="fail_test.txt",
            raw_file_storage_id=f"raw_{uuid4().hex[:8]}",
            text_storage_id=f"text_{uuid4().hex[:8]}",
            file_size_bytes=1024,
            content_md5_hash="fail123",
            correlation_id=correlation_id,
        )

        # This reveals the architectural debt - if Kafka fails, the operation fails
        with pytest.raises(
            Exception,
            match=r"\[KAFKA_PUBLISH_ERROR\].*Failed to publish essay slot assigned event to Kafka",
        ):
            await handler.handle_essay_content_provisioned(content_event, correlation_id)

        # This is the problem identified in the session context -
        # event publishing is in the critical path!
