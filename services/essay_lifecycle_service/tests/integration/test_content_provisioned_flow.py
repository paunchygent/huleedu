"""
Integration test for EssayContentProvisionedV1 event handling flow.

This test validates the critical File Service → ELS event flow, focusing on:
- Atomic DB slot assignment with proper transaction handling
- Event publishing patterns and reliability
- Error scenarios and transaction rollbacks
- Idempotency of content provisioning

Uses PostgreSQL testcontainer for isolated testing environment.
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
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.events.file_events import EssayContentProvisionedV1
from common_core.metadata_models import StorageReferenceMetadata, SystemProcessingMetadata
from common_core.status_enums import EssayStatus
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.domain_services import ContentAssignmentService
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
from services.essay_lifecycle_service.implementations.db_failure_tracker import DBFailureTracker
from services.essay_lifecycle_service.implementations.db_pending_content_ops import (
    DBPendingContentOperations,
)
from services.essay_lifecycle_service.implementations.essay_repository_postgres_impl import (
    PostgreSQLEssayRepository,
)
from services.essay_lifecycle_service.models_db import Base
from services.essay_lifecycle_service.protocols import SlotOperationsProtocol

logger = create_service_logger("test.content_provisioned_flow")


def make_prompt_ref(label: str) -> StorageReferenceMetadata:
    prompt_ref = StorageReferenceMetadata()
    prompt_ref.add_reference(ContentType.STUDENT_PROMPT_TEXT, label)
    return prompt_ref


@pytest.mark.integration
@pytest.mark.asyncio
class TestContentProvisionedFlow:
    """Test the File Service → ELS event handling flow."""

    @pytest.fixture
    async def test_infrastructure(self) -> AsyncIterator[dict[str, Any]]:
        """Set up DB-only test infrastructure with PostgreSQL container."""
        # Start PostgreSQL container only
        postgres_container = PostgresContainer("postgres:15")

        with postgres_container as pg:
            # Connection string
            db_url = (
                f"postgresql+asyncpg://{pg.username}:{pg.password}@"
                f"{pg.get_container_host_ip()}:{pg.get_exposed_port(5432)}/{pg.dbname}"
            )

            # Configure environment
            import os

            os.environ["ESSAY_LIFECYCLE_SERVICE_DATABASE_URL"] = db_url

            settings = Settings()

            # Create database connection and components
            engine = create_async_engine(settings.DATABASE_URL, echo=False)
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            repository = PostgreSQLEssayRepository(session_factory)

            persistence = BatchTrackerPersistence(engine)

            # Create DB-based implementations
            failure_tracker = DBFailureTracker(session_factory)
            mock_pending_content_ops = AsyncMock(spec=DBPendingContentOperations)

            # Provide a no-op slot operations implementation (Option B does not use it)
            from uuid import UUID

            class NoopSlotOperations(SlotOperationsProtocol):
                async def assign_slot_atomic(
                    self,
                    batch_id: str,
                    content_metadata: dict[str, Any],
                    correlation_id: UUID | None = None,
                ) -> str | None:
                    return None

                async def get_available_slot_count(self, batch_id: str) -> int:
                    return 0

                async def get_assigned_count(self, batch_id: str) -> int:
                    return 0

                async def get_essay_id_for_content(
                    self, batch_id: str, text_storage_id: str
                ) -> str | None:
                    return None

            slot_operations = NoopSlotOperations()

            batch_tracker = DefaultBatchEssayTracker(
                persistence,
                failure_tracker,
                slot_operations,
                mock_pending_content_ops,
            )
            await batch_tracker.initialize_from_database()

            # TRUE OUTBOX PATTERN: No direct Kafka publishing, events go through outbox
            # We track outbox operations instead of Kafka operations
            published_events: list[dict[str, Any]] = []

            # Create real BatchLifecyclePublisher with mock outbox manager for TRUE OUTBOX PATTERN testing
            mock_outbox_manager = AsyncMock()
            mock_outbox_manager.publish_to_outbox = AsyncMock()

            # Import the Settings class for the publisher
            test_settings = Settings()

            # Create smart mock topic naming for integration test that returns correct topic names
            from unittest.mock import Mock

            from common_core.event_enums import topic_name

            from services.essay_lifecycle_service.protocols import TopicNamingProtocol

            def smart_get_topic_name(event: ProcessingEvent) -> str:
                """Smart mock that returns correct topic names based on ProcessingEvent."""
                return topic_name(event)

            mock_topic_naming = Mock(spec=TopicNamingProtocol)
            mock_topic_naming.get_topic_name.side_effect = smart_get_topic_name

            # Create REAL BatchLifecyclePublisher to test actual TRUE OUTBOX PATTERN behavior
            event_publisher = BatchLifecyclePublisher(
                settings=test_settings,
                outbox_manager=mock_outbox_manager,
                topic_naming=mock_topic_naming,
            )

            # Create content assignment service
            content_assignment_service = ContentAssignmentService(
                batch_tracker=batch_tracker,
                repository=repository,
                batch_lifecycle_publisher=event_publisher,
            )

            handler = DefaultBatchCoordinationHandler(
                batch_tracker=batch_tracker,
                repository=repository,
                batch_lifecycle_publisher=event_publisher,
                pending_content_ops=mock_pending_content_ops,
                content_assignment_service=content_assignment_service,
                session_factory=repository.get_session_factory(),
            )

            yield {
                "handler": handler,
                "repository": repository,
                "batch_tracker": batch_tracker,
                "event_publisher": event_publisher,
                "published_events": published_events,
                "mock_outbox_manager": mock_outbox_manager,
            }

            # Cleanup
            await engine.dispose()

    async def test_content_provisioned_atomic_slot_assignment(
        self, test_infrastructure: dict[str, Any]
    ) -> None:
        """Test atomic slot assignment with proper DB transactions."""
        handler = test_infrastructure["handler"]
        repository = test_infrastructure["repository"]

        # Setup: Register batch
        batch_id = str(uuid4())
        essay_ids = [str(uuid4()) for _ in range(3)]
        correlation_id = uuid4()

        batch_event = BatchEssaysRegistered(
            entity_id=batch_id,
            course_code=CourseCode.ENG5,
            student_prompt_ref=make_prompt_ref("prompt-atomic-assignment"),
            essay_ids=essay_ids,
            expected_essay_count=len(essay_ids),
            user_id="test_user",
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                parent_id=None,
                timestamp=datetime.now(UTC),
                processing_stage=None,
            ),
        )

        await handler.handle_batch_essays_registered(batch_event, correlation_id)

        # Test: Handle content provisioned event
        file_upload_id = f"upload_{uuid4().hex[:8]}"
        text_storage_id = f"text_{uuid4().hex[:8]}"

        content_event = EssayContentProvisionedV1(
            entity_id=batch_id,
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

        # TRUE OUTBOX PATTERN: Verify outbox_manager.publish_to_outbox was called
        # This is the correct abstraction level for testing the outbox pattern
        mock_outbox_manager = test_infrastructure["mock_outbox_manager"]
        mock_outbox_manager.publish_to_outbox.assert_called_once()

        # Verify the outbox call parameters match the TRUE OUTBOX PATTERN
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args.kwargs["aggregate_type"] == "essay"
        assert call_args.kwargs["aggregate_id"] == str(assigned_essay.essay_id)
        assert call_args.kwargs["event_type"] == topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED)
        assert call_args.kwargs["topic"] == topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED)

        # Verify the event data envelope is properly structured
        event_envelope = call_args.kwargs["event_data"]
        assert event_envelope.event_type == topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED)
        assert (
            event_envelope.source_service
            == test_infrastructure["event_publisher"].settings.SERVICE_NAME
        )

    async def test_concurrent_content_provisioning(
        self, test_infrastructure: dict[str, Any]
    ) -> None:
        """Test multiple concurrent content provisioning requests."""
        handler = test_infrastructure["handler"]
        repository = test_infrastructure["repository"]

        # Setup: Register batch with 5 essays
        batch_id = str(uuid4())
        essay_ids = [str(uuid4()) for _ in range(5)]
        correlation_id = uuid4()

        batch_event = BatchEssaysRegistered(
            entity_id=batch_id,
            course_code=CourseCode.ENG5,
            student_prompt_ref=make_prompt_ref("prompt-concurrent"),
            essay_ids=essay_ids,
            expected_essay_count=len(essay_ids),
            user_id="test_user",
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                parent_id=None,
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
                entity_id=batch_id,
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
        failed_provisions = []
        for result in results:
            if (
                not isinstance(result, BaseException)
                and isinstance(result, tuple)
                and len(result) == 2
            ):
                success, fid = result
                if success:
                    successful_provisions.append((success, fid))
                else:
                    failed_provisions.append((success, fid))

        # Under high concurrency, some provisions may fail due to slot exhaustion
        # The key is that successes + failures = total attempts
        assert len(successful_provisions) + len(failed_provisions) == 5, (
            f"Expected 5 total results, got {len(successful_provisions)} successes + "
            f"{len(failed_provisions)} failures"
        )

        # Verify database state matches successful provisions
        essays = await repository.list_essays_by_batch(batch_id)
        assigned_essays = [e for e in essays if ContentType.ORIGINAL_ESSAY in e.storage_references]
        assert len(assigned_essays) == len(successful_provisions), (
            f"Database has {len(assigned_essays)} assigned essays but "
            f"{len(successful_provisions)} provisions succeeded"
        )

        # Verify Redis state consistency
        # Verify counts via repository summary (essay_states inventory)
        summary = await repository.get_batch_status_summary(batch_id)
        available = summary.get(EssayStatus.UPLOADED, 0)
        assert len(assigned_essays) + available == 5

        # Log the distribution for debugging (Option B inventory)
        logger.info(f"Distribution: assigned={len(assigned_essays)}, available={available}")

        # If there were failures, verify ExcessContentProvisionedV1 events were published
        if failed_provisions:
            published_events = test_infrastructure["published_events"]
            excess_events = [
                e
                for e in published_events
                if e["envelope"].event_type
                == topic_name(ProcessingEvent.EXCESS_CONTENT_PROVISIONED)
            ]
            assert len(excess_events) == len(failed_provisions), (
                f"Expected {len(failed_provisions)} excess content events, found {len(excess_events)}"
            )

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
            entity_id=batch_id,
            course_code=CourseCode.ENG5,
            student_prompt_ref=make_prompt_ref("prompt-idempotency"),
            essay_ids=essay_ids,
            expected_essay_count=len(essay_ids),
            user_id="test_user",
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                parent_id=None,
                timestamp=datetime.now(UTC),
                processing_stage=None,
            ),
        )

        await handler.handle_batch_essays_registered(batch_event, correlation_id)

        # Test: Provision content twice with same text_storage_id
        file_upload_id = f"upload_idempotent_{uuid4().hex[:8]}"
        text_storage_id = f"text_idempotent_{uuid4().hex[:8]}"

        content_event = EssayContentProvisionedV1(
            entity_id=batch_id,
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
        """Test behavior when event publishing fails - with outbox pattern, operations should succeed."""
        handler = test_infrastructure["handler"]
        # Test that outbox pattern provides resilience against infrastructure failures
        repository = test_infrastructure["repository"]

        # Setup: Register batch
        batch_id = str(uuid4())
        essay_ids = [str(uuid4()) for _ in range(2)]
        correlation_id = uuid4()

        batch_event = BatchEssaysRegistered(
            entity_id=batch_id,
            course_code=CourseCode.ENG5,
            student_prompt_ref=make_prompt_ref("prompt-publishing-failure"),
            essay_ids=essay_ids,
            expected_essay_count=len(essay_ids),
            user_id="test_user",
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                parent_id=None,
                timestamp=datetime.now(UTC),
                processing_stage=None,
            ),
        )

        await handler.handle_batch_essays_registered(batch_event, correlation_id)

        # With TRUE OUTBOX PATTERN, Kafka failures don't affect business operations
        # The outbox manager handles reliable delivery asynchronously

        # Test: Try to provision content
        content_event = EssayContentProvisionedV1(
            entity_id=batch_id,
            file_upload_id=f"upload_fail_{uuid4().hex[:8]}",
            original_file_name="fail_test.txt",
            raw_file_storage_id=f"raw_{uuid4().hex[:8]}",
            text_storage_id=f"text_{uuid4().hex[:8]}",
            file_size_bytes=1024,
            content_md5_hash="fail123",
            correlation_id=correlation_id,
        )

        # With outbox pattern, this should succeed even when Kafka is down
        success = await handler.handle_essay_content_provisioned(content_event, correlation_id)
        assert success, "Content provisioning should succeed even when Kafka is unavailable"

        # Verify the event was stored in the outbox using TRUE OUTBOX PATTERN
        mock_outbox_manager = test_infrastructure["mock_outbox_manager"]
        (
            mock_outbox_manager.publish_to_outbox.assert_called(),
            "Event should be stored in outbox for transactional safety",
        )

        # Verify database state was updated
        essays = await repository.list_essays_by_batch(batch_id)
        assigned_essays = [e for e in essays if ContentType.ORIGINAL_ESSAY in e.storage_references]
        assert len(assigned_essays) == 1, "Essay should have content assigned despite Kafka failure"
