"""
Integration test for pending content race condition fix.

This test validates the critical race condition scenario where:
1. Essay content arrives BEFORE batch registration (stored as pending)
2. Batch registration occurs with essay database records creation
3. Pending content processing updates essay status to READY_FOR_PROCESSING
4. State machine allows proper transitions (spellcheck initiation)

This reproduces the exact issue found in E2E test where essay f5aee829
remained in 'uploaded' status instead of transitioning to 'ready_for_processing'.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core.domain_enums import ContentType, CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.events.file_events import EssayContentProvisionedV1
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import EssayStatus
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.redis_client import RedisClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.essay_state_machine import EssayStateMachine
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
from services.essay_lifecycle_service.implementations.essay_repository_postgres_impl import (
    PostgreSQLEssayRepository,
)
from services.essay_lifecycle_service.implementations.redis_batch_queries import (
    RedisBatchQueries,
)
from services.essay_lifecycle_service.implementations.redis_batch_state import (
    RedisBatchState,
)
from services.essay_lifecycle_service.implementations.redis_failure_tracker import (
    RedisFailureTracker,
)
from services.essay_lifecycle_service.implementations.redis_pending_content_ops import (
    RedisPendingContentOperations,
)
from services.essay_lifecycle_service.implementations.redis_script_manager import (
    RedisScriptManager,
)
from services.essay_lifecycle_service.implementations.redis_slot_operations import (
    RedisSlotOperations,
)
from services.essay_lifecycle_service.models_db import Base
from services.essay_lifecycle_service.protocols import TopicNamingProtocol

logger = create_service_logger("test_pending_content_race_condition")


class TestPendingContentRaceCondition:
    """Test suite for pending content race condition scenarios."""

    @pytest.fixture
    async def test_infrastructure(self) -> AsyncIterator[dict[str, Any]]:
        """Set up complete ELS integration test infrastructure."""
        # Start PostgreSQL container
        postgres_container = PostgresContainer("postgres:15", driver="asyncpg")
        postgres_container.start()

        # Start Redis container
        redis_container = RedisContainer("redis:7")
        redis_container.start()

        redis_client = None
        repository = None
        engine = None

        try:
            # Connection strings
            redis_url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"
            db_url = (
                f"postgresql+asyncpg://{postgres_container.username}:{postgres_container.password}@"
                f"{postgres_container.get_container_host_ip()}:{postgres_container.get_exposed_port(5432)}/{postgres_container.dbname}"
            )

            # Configure environment
            import os

            os.environ["ESSAY_LIFECYCLE_SERVICE_DATABASE_URL"] = db_url
            os.environ["ESSAY_LIFECYCLE_SERVICE_REDIS_URL"] = redis_url

            settings = Settings()

            # Initialize Redis client
            redis_client = RedisClient(client_id="test-els-race-condition", redis_url=redis_url)
            await redis_client.start()

            # Initialize Redis script manager
            redis_script_manager = RedisScriptManager(redis_client)

            # Initialize Redis operations
            batch_state = RedisBatchState(redis_client, redis_script_manager)
            batch_queries = RedisBatchQueries(redis_client, redis_script_manager)
            failure_tracker = RedisFailureTracker(redis_client, redis_script_manager)
            slot_operations = RedisSlotOperations(redis_client, redis_script_manager)
            pending_content_ops = RedisPendingContentOperations(redis_client)

            # Initialize repository
            engine = create_async_engine(settings.DATABASE_URL, echo=False)
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            repository = PostgreSQLEssayRepository(session_factory)

            persistence = BatchTrackerPersistence(engine)

            # Initialize batch tracker with REAL pending content ops (not mocked)
            batch_tracker = DefaultBatchEssayTracker(
                persistence,
                batch_state,
                batch_queries,
                failure_tracker,
                slot_operations,
                pending_content_ops,  # Real implementation to test the race condition
            )
            await batch_tracker.initialize_from_database()

            # Mock outbox manager for event publishing
            mock_outbox_manager = AsyncMock()
            mock_outbox_manager.publish_to_outbox = AsyncMock()

            # Create topic naming mock
            def smart_get_topic_name(event: ProcessingEvent) -> str:
                return topic_name(event)

            mock_topic_naming = Mock(spec=TopicNamingProtocol)
            mock_topic_naming.get_topic_name.side_effect = smart_get_topic_name

            # Create event publisher
            event_publisher = BatchLifecyclePublisher(
                settings=settings,
                outbox_manager=mock_outbox_manager,
                topic_naming=mock_topic_naming,
            )

            # Create content assignment service
            from services.essay_lifecycle_service.domain_services import ContentAssignmentService

            content_assignment_service = ContentAssignmentService(
                batch_tracker=batch_tracker,
                repository=repository,
                batch_lifecycle_publisher=event_publisher,
            )

            # Create handler
            handler = DefaultBatchCoordinationHandler(
                batch_tracker=batch_tracker,
                repository=repository,
                batch_lifecycle_publisher=event_publisher,
                pending_content_ops=pending_content_ops,
                content_assignment_service=content_assignment_service,
                session_factory=repository.get_session_factory(),
            )

            yield {
                "handler": handler,
                "repository": repository,
                "batch_tracker": batch_tracker,
                "pending_content_ops": pending_content_ops,
                "slot_operations": slot_operations,
                "redis_client": redis_client,
                "event_publisher": event_publisher,
                "mock_outbox_manager": mock_outbox_manager,
            }

        finally:
            # Cleanup
            if redis_client:
                await redis_client.stop()
            if engine:
                await engine.dispose()
            postgres_container.stop()
            redis_container.stop()

    async def test_pending_content_before_batch_registration_race_condition(
        self, test_infrastructure: dict[str, Any]
    ) -> None:
        """
        Test the specific race condition where content arrives before batch registration.

        This reproduces the exact scenario that caused essay f5aee829-da97-4d9e-96e4-f121ad508f9a
        to remain in 'uploaded' status instead of transitioning to 'ready_for_processing'.
        """
        handler = test_infrastructure["handler"]
        repository = test_infrastructure["repository"]
        batch_tracker = test_infrastructure["batch_tracker"]
        pending_content_ops = test_infrastructure["pending_content_ops"]

        # Step 1: Create content BEFORE batch registration (the race condition scenario)
        batch_id = str(uuid4())
        essay_id = str(uuid4())
        text_storage_id = str(uuid4())
        correlation_id = uuid4()

        logger.info(f"Testing race condition with batch_id: {batch_id}, essay_id: {essay_id}")

        # CRITICAL: Store content as pending BEFORE batch exists
        content_metadata = {
            "original_file_name": "test_essay.docx",
            "file_upload_id": str(uuid4()),
            "raw_file_storage_id": str(uuid4()),
            "file_size_bytes": 1000,
            "content_md5_hash": "test_hash_123",
            "correlation_id": str(correlation_id),
        }

        await pending_content_ops.store_pending_content(batch_id, text_storage_id, content_metadata)

        # Verify content is stored as pending
        pending_content = await pending_content_ops.get_pending_content(batch_id)
        assert len(pending_content) == 1
        assert pending_content[0]["text_storage_id"] == text_storage_id

        logger.info("✓ Content stored as pending before batch registration")

        # Step 2: Register batch (this should process pending content and update essay status)
        essay_ids = [essay_id]  # Single essay for focused testing

        batch_registered_event = BatchEssaysRegistered(
            entity_id=batch_id,
            user_id="test_user",
            course_code=CourseCode.ENG5,
            class_id=None,  # GUEST batch
            essay_instructions="Test instructions",
            essay_ids=essay_ids,
            expected_essay_count=len(essay_ids),
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
            ),
        )

        # This should:
        # 1. Register batch in Redis
        # 2. Create essay records in database with 'uploaded' status
        # 3. Process pending content
        # 4. Update essay database record with content and 'ready_for_processing' status
        result = await handler.handle_batch_essays_registered(
            batch_registered_event, correlation_id
        )
        assert result is True

        logger.info("✓ Batch registration completed")

        # Step 3: Verify pending content was processed
        remaining_pending = await pending_content_ops.get_pending_content(batch_id)
        assert len(remaining_pending) == 0, "Pending content should be processed and removed"

        logger.info("✓ Pending content was processed and removed")

        # Step 4: Verify essay database record has correct status and content
        essay_state = await repository.get_essay_state(essay_id)
        assert essay_state is not None, f"Essay {essay_id} should exist in database"

        # CRITICAL: Essay should have READY_FOR_PROCESSING status, not uploaded
        assert essay_state.current_status == EssayStatus.READY_FOR_PROCESSING, (
            f"Essay {essay_id} should have READY_FOR_PROCESSING status, "
            f"but has {essay_state.current_status}. This indicates the race condition bug."
        )

        # Verify content information was stored
        storage_refs = essay_state.storage_references
        assert ContentType.ORIGINAL_ESSAY.value in storage_refs
        assert storage_refs[ContentType.ORIGINAL_ESSAY.value] == text_storage_id

        logger.info(f"✓ Essay {essay_id} has correct status: {essay_state.current_status}")
        logger.info(f"✓ Essay {essay_id} has correct content reference: {text_storage_id}")

        # Step 5: Verify state machine can transition from READY_FOR_PROCESSING
        state_machine = EssayStateMachine(essay_id, EssayStatus.READY_FOR_PROCESSING)

        # This should succeed now (was failing before the fix)
        can_initiate_spellcheck = state_machine.can_trigger("CMD_INITIATE_SPELLCHECK")
        assert can_initiate_spellcheck, (
            f"State machine should allow spellcheck initiation from READY_FOR_PROCESSING, "
            f"but got valid triggers: {state_machine.get_valid_triggers()}"
        )

        # Test the actual transition
        transition_result = state_machine.cmd_initiate_spellcheck()
        assert transition_result is True, "Spellcheck initiation should succeed"
        assert state_machine.current_status == EssayStatus.AWAITING_SPELLCHECK

        logger.info(
            "✓ State machine transition from READY_FOR_PROCESSING to AWAITING_SPELLCHECK succeeded"
        )

        # Step 6: Verify batch completion - batch might be cleaned up if complete
        batch_status = await batch_tracker.get_batch_status(batch_id)
        if batch_status is not None:
            # Batch still exists, verify status
            assert batch_status["ready_count"] >= 1
            logger.info("✓ Batch status correctly shows essay as ready for processing")
        else:
            # Batch was cleaned up after completion - this is expected for complete batches
            logger.info("✓ Batch was cleaned up after completion (expected for complete batches)")

        logger.info("🎉 Race condition test PASSED - fix is working correctly!")

    async def test_normal_flow_still_works(self, test_infrastructure: dict[str, Any]) -> None:
        """Verify that normal flow (batch registration before content) still works correctly."""
        handler = test_infrastructure["handler"]
        repository = test_infrastructure["repository"]

        # Step 1: Register batch FIRST (normal flow)
        batch_id = str(uuid4())
        essay_id = str(uuid4())
        correlation_id = uuid4()

        batch_registered_event = BatchEssaysRegistered(
            entity_id=batch_id,
            user_id="test_user",
            course_code=CourseCode.ENG5,
            class_id=None,
            essay_instructions="Test instructions",
            essay_ids=[essay_id],
            expected_essay_count=1,
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
            ),
        )

        result = await handler.handle_batch_essays_registered(
            batch_registered_event, correlation_id
        )
        assert result is True

        # Step 2: Send content AFTER batch registration (normal flow)
        text_storage_id = str(uuid4())

        content_provisioned_event = EssayContentProvisionedV1(
            entity_id=batch_id,
            text_storage_id=text_storage_id,
            original_file_name="normal_flow_essay.docx",
            file_upload_id=str(uuid4()),
            raw_file_storage_id=str(uuid4()),
            file_size_bytes=1500,
            content_md5_hash="normal_hash_456",
            correlation_id=correlation_id,
        )

        result = await handler.handle_essay_content_provisioned(
            content_provisioned_event, correlation_id
        )
        assert result is True

        # Step 3: Verify essay has correct status
        essay_state = await repository.get_essay_state(essay_id)
        assert essay_state is not None
        assert essay_state.current_status == EssayStatus.READY_FOR_PROCESSING

        logger.info("✓ Normal flow (batch then content) still works correctly")
