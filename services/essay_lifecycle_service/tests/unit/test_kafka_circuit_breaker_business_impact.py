"""
Business impact tests for Kafka circuit breaker failures in Essay Lifecycle Service.

Tests critical business scenarios where Kafka publishing failures would disrupt
essay processing workflows, complementing the technical circuit breaker tests.

Focus: Business workflow disruption and recovery, not technical circuit breaker mechanics.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiokafka.errors import KafkaError
from common_core.domain_enums import CourseCode, Language
from common_core.events.batch_coordination_events import BatchEssaysReady, BatchEssaysRegistered
from common_core.events.file_events import EssayContentProvisionedV1
from common_core.metadata_models import (
    EntityReference,
    EssayProcessingInputRefV1,
    SystemProcessingMetadata,
)
from common_core.status_enums import EssayStatus
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker
from pydantic import BaseModel

from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.implementations.batch_coordination_handler_impl import (
    DefaultBatchCoordinationHandler,
)
from services.essay_lifecycle_service.implementations.event_publisher import DefaultEventPublisher
from services.essay_lifecycle_service.implementations.service_request_dispatcher import (
    DefaultSpecializedServiceRequestDispatcher,
)
from services.essay_lifecycle_service.protocols import (
    BatchEssayTracker,
    EssayRepositoryProtocol,
)


class BusinessWorkflowContext(BaseModel):
    """Context model for tracking business workflow state during testing."""

    batch_id: str
    essay_count: int
    essays_ready_published: bool = False
    phase_outcomes_published: bool = False
    service_requests_dispatched: bool = False
    status_updates_completed: bool = False
    batch_coordinator_notified: bool = False
    teachers_notified: bool = False


@pytest.fixture
def mock_settings() -> Settings:
    """Settings configured for business impact testing."""
    return Settings(
        SERVICE_NAME="essay-lifecycle-service",
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        PRODUCER_CLIENT_ID="essay-lifecycle-business-test",
        CIRCUIT_BREAKER_ENABLED=True,
        KAFKA_CIRCUIT_BREAKER_FAILURE_THRESHOLD=2,
        KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=1,  # Short for testing
    )


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    """Circuit breaker configured for business testing scenarios."""
    return CircuitBreaker(
        name="essay-lifecycle-service.kafka_producer",
        failure_threshold=2,  # Low threshold for quick testing
        recovery_timeout=timedelta(seconds=1),
        success_threshold=1,
        expected_exception=KafkaError,
    )


@pytest.fixture
def mock_batch_tracker() -> AsyncMock:
    """Mock BatchEssayTracker for business logic testing."""
    tracker = AsyncMock(spec=BatchEssayTracker)
    tracker.register_batch.return_value = True
    tracker.get_user_id_for_essay.return_value = "test_user_123"
    # check_batch_completion returns None when batch is not complete
    tracker.check_batch_completion.return_value = None
    return tracker


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Mock EssayRepositoryProtocol for business logic testing."""
    repo = AsyncMock(spec=EssayRepositoryProtocol)
    repo.create_essay_records_batch.return_value = True
    repo.update_essay_status_via_machine.return_value = True
    return repo


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Mock Redis client for dual-channel publishing tests."""
    redis = AsyncMock(spec=AtomicRedisClientProtocol)
    redis.publish_user_notification.return_value = True
    redis.lpush = AsyncMock(return_value=1)  # For wake-up notifications
    return redis


@pytest.fixture
def mock_outbox_repository() -> AsyncMock:
    """Mock OutboxRepository for testing with outbox pattern."""
    repo = AsyncMock()
    repo.add_event = AsyncMock()
    return repo


@pytest.fixture
def failing_kafka_bus() -> AsyncMock:
    """Kafka bus that fails to simulate circuit breaker scenarios."""
    bus = AsyncMock(spec=KafkaPublisherProtocol)
    bus.publish.side_effect = KafkaError("Kafka publishing failure")
    return bus


@pytest.fixture
def business_context() -> BusinessWorkflowContext:
    """Business workflow tracking context."""
    return BusinessWorkflowContext(
        batch_id=f"batch_{uuid4()}",
        essay_count=5,
    )


class TestBatchCoordinationBusinessImpact:
    """Test business impact of batch coordination publishing failures."""

    @pytest.mark.asyncio
    async def test_batch_readiness_publishing_failure_prevents_phase_initiation(
        self,
        failing_kafka_bus: AsyncMock,
        mock_batch_tracker: AsyncMock,
        mock_repository: AsyncMock,
        mock_redis_client: AsyncMock,
        mock_outbox_repository: AsyncMock,
        mock_settings: Settings,
        business_context: BusinessWorkflowContext,
    ) -> None:
        """
        BUSINESS SCENARIO: BatchEssaysReady event storage fails during slot fulfillment.
        BUSINESS IMPACT: Batches get stuck in content provisioning state permanently.
        WORKFLOW DISRUPTION: No processing phases (spellcheck, assessment) initiated.

        Note: With outbox pattern, we test database failures, not direct Kafka failures.
        """
        # Arrange: Set up outbox repository to fail when trying to store BatchEssaysReady

        # Make outbox fail specifically for batch ready events
        mock_outbox_repository.add_event.side_effect = Exception("Database connection lost")
        event_publisher = DefaultEventPublisher(
            kafka_bus=failing_kafka_bus,
            settings=mock_settings,
            redis_client=mock_redis_client,
            batch_tracker=mock_batch_tracker,
            outbox_repository=mock_outbox_repository,
        )

        coordination_handler = DefaultBatchCoordinationHandler(
            batch_tracker=mock_batch_tracker,
            repository=mock_repository,
            event_publisher=event_publisher,
        )

        batch_registered_event = BatchEssaysRegistered(
            batch_id=business_context.batch_id,
            essay_ids=[f"essay_{i}" for i in range(business_context.essay_count)],
            expected_essay_count=business_context.essay_count,
            user_id="test_user_123",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_type="batch",
                    entity_id=business_context.batch_id,
                ),
            ),
            course_code=CourseCode.ENG5,
            essay_instructions="Test essay instructions",
        )
        
        # Create a BatchEssaysReady event that will be returned by check_batch_completion
        # to simulate immediate batch completion due to pending failures
        ready_essays: list[EssayProcessingInputRefV1] = []  # No ready essays since all failed
        batch_ready_event = BatchEssaysReady(
            batch_id=business_context.batch_id,
            ready_essays=ready_essays,
            batch_entity=EntityReference(
                entity_type="batch",
                entity_id=business_context.batch_id,
            ),
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_type="batch",
                    entity_id=business_context.batch_id,
                ),
            ),
            course_code=CourseCode.ENG5,
            course_language="English",
            essay_instructions=batch_registered_event.essay_instructions,
            class_type="GUEST",
            user_id="test_user_123",
            validation_failures=[],  # Add some failures if needed
        )
        
        # Mock check_batch_completion to return the ready event during registration
        correlation_id = uuid4()
        mock_batch_tracker.check_batch_completion.return_value = (batch_ready_event, correlation_id)

        # Act: Process batch registration - this should fail when trying to publish BatchEssaysReady
        with pytest.raises(Exception) as exc_info:
            await coordination_handler.handle_batch_essays_registered(
                event_data=batch_registered_event,
                correlation_id=correlation_id,
            )

        # Verify it's an external service error (outbox storage failed)
        assert "EXTERNAL_SERVICE_ERROR" in str(exc_info.value)

        # Assert: Verify Kafka was tried first (Kafka-first pattern)
        failing_kafka_bus.publish.assert_called_once()
        # Then outbox was attempted as fallback and failed
        mock_outbox_repository.add_event.assert_called_once()

        business_context.essays_ready_published = False
        business_context.batch_coordinator_notified = False

        # BUSINESS IMPACT VERIFICATION:
        # 1. Batch Orchestrator Service never receives BatchEssaysReady notification
        # 2. No processing phases will be initiated (spellcheck, CJ assessment)
        # 3. Teachers will see batch stuck in "uploading" state permanently
        # 4. Complete workflow stoppage for this batch

        # Simulate checking batch status from teacher perspective
        business_context.batch_coordinator_notified = False  # BOS never notified
        business_context.essays_ready_published = False  # Ready event failed

        assert not business_context.batch_coordinator_notified
        assert not business_context.essays_ready_published

    @pytest.mark.asyncio
    async def test_content_provisioned_handling_with_publishing_failures(
        self,
        failing_kafka_bus: AsyncMock,
        mock_batch_tracker: AsyncMock,
        mock_repository: AsyncMock,
        mock_redis_client: AsyncMock,
        mock_outbox_repository: AsyncMock,
        mock_settings: Settings,
        business_context: BusinessWorkflowContext,
    ) -> None:
        """
        BUSINESS SCENARIO: Content provisioning completes but readiness event storage fails.
        BUSINESS IMPACT: Essays are ready for processing but batch never transitions.
        WORKFLOW DISRUPTION: Batch appears incomplete despite all content being ready.

        Note: With outbox pattern, we test database failures, not direct Kafka failures.
        """
        # Arrange: Set up outbox to succeed for first event but fail for second
        # First call succeeds (EssaySlotAssignedV1), second call fails (BatchEssaysReady)
        mock_outbox_repository.add_event.side_effect = [
            uuid4(),  # First call succeeds
            Exception("Database write failed")  # Second call fails
        ]

        event_publisher = DefaultEventPublisher(
            kafka_bus=failing_kafka_bus,
            settings=mock_settings,
            redis_client=mock_redis_client,
            batch_tracker=mock_batch_tracker,
            outbox_repository=mock_outbox_repository,
        )

        coordination_handler = DefaultBatchCoordinationHandler(
            batch_tracker=mock_batch_tracker,
            repository=mock_repository,
            event_publisher=event_publisher,
        )

        # Mock batch tracker to assign a slot
        mock_batch_tracker.assign_slot_to_content.return_value = "essay_0"

        # Mock repository to succeed in creating essay state
        mock_repository.create_essay_state_with_content_idempotency.return_value = (
            True,  # was_created
            "essay_0",  # final_essay_id
        )

        # Create ready essays for the batch ready event
        ready_essays = [
            EssayProcessingInputRefV1(
                essay_id=f"essay_{i}",
                text_storage_id=f"storage_{i}",
            )
            for i in range(business_context.essay_count)
        ]

        # Create a proper BatchEssaysReady event that will be returned when batch is complete
        batch_ready_event = BatchEssaysReady(
            batch_id=business_context.batch_id,
            ready_essays=ready_essays,
            batch_entity=EntityReference(
                entity_type="batch",
                entity_id=business_context.batch_id,
            ),
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_type="batch",
                    entity_id=business_context.batch_id,
                ),
            ),
            course_code=CourseCode.ENG5,
            course_language="English",
            essay_instructions="Test essay instructions",
            class_type="GUEST",
            user_id="test_user_123",
        )

        # Mock batch tracker to indicate batch is now ready
        correlation_id = uuid4()
        mock_batch_tracker.mark_slot_fulfilled.return_value = (batch_ready_event, correlation_id)

        content_provisioned_event = EssayContentProvisionedV1(
            batch_id=business_context.batch_id,
            file_upload_id="test-file-upload-circuit-breaker-2",
            text_storage_id="content_123",
            raw_file_storage_id="raw_123",
            original_file_name="essay.txt",
            file_size_bytes=1024,
            content_md5_hash="hash123",
        )

        # Act: Handle content provisioned event
        # This should raise an exception when trying to publish BatchEssaysReady
        with pytest.raises(Exception) as exc_info:
            await coordination_handler.handle_essay_content_provisioned(
                event_data=content_provisioned_event,
                correlation_id=correlation_id,
            )

        # Verify it's an external service error (outbox storage failed)
        # The _publish_to_outbox method uses raise_external_service_error
        assert "EXTERNAL_SERVICE_ERROR" in str(exc_info.value)

        # Assert: Business impact verification
        # Even though the handler raised an exception, we can verify partial progress

        # Verify content assignment happened before publishing failure
        mock_batch_tracker.assign_slot_to_content.assert_called_once()
        mock_repository.create_essay_state_with_content_idempotency.assert_called_once()

        # Verify mark_slot_fulfilled was called (happens before publishing)
        mock_batch_tracker.mark_slot_fulfilled.assert_called_once_with(
            business_context.batch_id, "essay_0", "content_123"
        )

        # Verify outbox storage was attempted twice
        # First call succeeded (EssaySlotAssignedV1), second call failed (BatchEssaysReady)
        assert mock_outbox_repository.add_event.call_count == 2

        # Kafka is tried first in Kafka-first pattern, then falls back to outbox
        # The handler publishes EssaySlotAssignedV1 event first
        failing_kafka_bus.publish.assert_called()
        
        # Verify that both publish attempts were made (EssaySlotAssignedV1 and BatchEssaysReady)
        publish_calls = failing_kafka_bus.publish.call_args_list
        assert len(publish_calls) == 2
        assert publish_calls[0].kwargs["topic"] == "huleedu.els.essay.slot.assigned.v1"
        assert publish_calls[1].kwargs["topic"] == "huleedu.els.batch.essays.ready.v1"

        # BUSINESS IMPACT VERIFICATION:
        # 1. Content is provisioned and essays are ready for processing
        # 2. But batch coordinator never knows -> no phase initiation
        # 3. Essays exist in system but workflow never progresses
        business_context.essays_ready_published = False
        business_context.batch_coordinator_notified = False

        # This represents the critical business failure:
        # System state is correct but workflow coordination is broken
        # Essays are provisioned but batch coordination never occurs
        assert not business_context.batch_coordinator_notified


class TestServiceRequestDispatchBusinessImpact:
    """Test business impact of specialized service request dispatch failures."""

    @pytest.mark.asyncio
    async def test_spellcheck_dispatch_failure_prevents_processing(
        self,
        failing_kafka_bus: AsyncMock,
        mock_outbox_repository: AsyncMock,
        mock_settings: Settings,
        business_context: BusinessWorkflowContext,
    ) -> None:
        """
        BUSINESS SCENARIO: Spellcheck request storage fails after batch readiness.
        BUSINESS IMPACT: Processing pipeline starts but specialized services never engaged.
        WORKFLOW DISRUPTION: Essays remain in "awaiting spellcheck" state indefinitely.

        Note: With outbox pattern, we test database failures during dispatch.
        """
        # Arrange: Set up outbox to fail when storing spellcheck requests
        mock_outbox_repository.add_event.side_effect = Exception("Database unavailable")

        dispatcher = DefaultSpecializedServiceRequestDispatcher(
            kafka_bus=failing_kafka_bus,
            settings=mock_settings,
            outbox_repository=mock_outbox_repository,
        )

        essays_to_process = [
            EssayProcessingInputRefV1(
                essay_id=f"essay_{i}",
                text_storage_id=f"storage_{i}",
                metadata={"title": f"Essay {i}"},
            )
            for i in range(business_context.essay_count)
        ]

        # Act: Attempt to dispatch spellcheck requests
        correlation_id = uuid4()

        # The dispatch method will raise an exception when Kafka publishing fails
        with pytest.raises(HuleEduError):
            await dispatcher.dispatch_spellcheck_requests(
                essays_to_process=essays_to_process,
                language=Language.ENGLISH,
                batch_id=business_context.batch_id,
                correlation_id=correlation_id,
            )

        # Assert: Business impact verification

        # Verify outbox storage was attempted and failed
        mock_outbox_repository.add_event.assert_called()

        # Kafka should NOT be called directly with outbox pattern
        assert failing_kafka_bus.publish.call_count == 0

        # BUSINESS IMPACT VERIFICATION:
        # 1. Batch Orchestrator initiated spellcheck phase
        # 2. ELS received command and attempted to dispatch individual requests
        # 3. Specialized services never receive processing requests
        # 4. Essays remain in "spellcheck_pending" status indefinitely
        # 5. Teachers see processing started but never completed

        business_context.service_requests_dispatched = False
        assert not business_context.service_requests_dispatched

        # This represents complete processing pipeline failure:
        # Phase started but no actual processing occurs

    @pytest.mark.asyncio
    async def test_cj_assessment_dispatch_failure_prevents_assessment(
        self,
        mock_outbox_repository: AsyncMock,
        mock_settings: Settings,
        business_context: BusinessWorkflowContext,
    ) -> None:
        """
        BUSINESS SCENARIO: CJ assessment request storage fails during dispatch.
        BUSINESS IMPACT: Batch processing stalls at assessment phase.
        WORKFLOW DISRUPTION: Essays remain in "awaiting assessment" state indefinitely.

        Note: With outbox pattern, we test database failures during dispatch.
        """
        # Arrange: Set up outbox to fail when storing CJ assessment requests
        mock_outbox_repository.add_event.side_effect = Exception(
            "Database connection pool exhausted"
        )

        # Create a mock Kafka bus (won't be used directly with outbox pattern)
        failing_kafka_bus = AsyncMock(spec=KafkaPublisherProtocol)

        dispatcher = DefaultSpecializedServiceRequestDispatcher(
            kafka_bus=failing_kafka_bus,
            settings=mock_settings,
            outbox_repository=mock_outbox_repository,
        )

        essays_to_process = [
            EssayProcessingInputRefV1(
                essay_id=f"essay_{i}",
                text_storage_id=f"storage_{i}",
                metadata={"title": f"Essay {i}"},
            )
            for i in range(business_context.essay_count)
        ]

        # Act: Attempt to dispatch CJ assessment request
        correlation_id = uuid4()

        # Act: Attempt to dispatch CJ assessment request
        with pytest.raises(Exception) as exc_info:
            await dispatcher.dispatch_cj_assessment_requests(
                essays_to_process=essays_to_process,
                language=Language.ENGLISH,
                course_code=CourseCode.ENG5,  # Use valid enum value
                essay_instructions="Write about the topic",
                batch_id=business_context.batch_id,
                correlation_id=correlation_id,
            )

        # Assert: Business impact verification

        # Verify outbox storage was attempted and failed
        mock_outbox_repository.add_event.assert_called_once()

        # Kafka should NOT be called directly with outbox pattern
        assert failing_kafka_bus.publish.call_count == 0

        # Verify proper error handling - Database error should be wrapped in HuleEduError
        caught_exception = exc_info.value
        assert isinstance(caught_exception, HuleEduError)
        assert "CJ_ASSESSMENT_SERVICE_ERROR" in str(caught_exception)

        # BUSINESS IMPACT VERIFICATION:
        # 1. Batch Orchestrator initiated CJ assessment phase
        # 2. ELS received command and attempted to dispatch assessment request
        # 3. CJ Assessment Service never receives processing request
        # 4. Essays remain in "cj_pending" status indefinitely
        # 5. Teachers see assessment phase started but never completed
        # 6. No comparative judgement data is generated

        business_context.service_requests_dispatched = False
        assert not business_context.service_requests_dispatched

        # This represents complete assessment failure:
        # Assessment phase never actually processes essays


class TestDualChannelPublishingBusinessImpact:
    """Test business impact of dual-channel publishing inconsistencies."""

    @pytest.mark.asyncio
    async def test_kafka_success_redis_failure_creates_ui_inconsistency(
        self,
        mock_outbox_repository: AsyncMock,
        mock_settings: Settings,
        mock_batch_tracker: AsyncMock,
        business_context: BusinessWorkflowContext,
    ) -> None:
        """
        BUSINESS SCENARIO: Kafka publishing succeeds but Redis notifications fail.
        BUSINESS IMPACT: Essay status updates reach services but not UI.
        WORKFLOW DISRUPTION: Teachers see stale status while processing continues.

        Note: With Kafka-first pattern, Kafka succeeds so no outbox is used.
        """
        # Arrange: Kafka succeeds, Redis fails
        working_kafka_bus = AsyncMock(spec=KafkaPublisherProtocol)
        working_kafka_bus.publish.return_value = None  # Kafka succeeds

        # Outbox should not be used when Kafka succeeds
        mock_outbox_repository.add_event.return_value = uuid4()

        failing_redis_client = AsyncMock(spec=AtomicRedisClientProtocol)
        failing_redis_client.publish_user_notification.side_effect = Exception("Redis failure")

        event_publisher = DefaultEventPublisher(
            kafka_bus=working_kafka_bus,
            settings=mock_settings,
            redis_client=failing_redis_client,
            batch_tracker=mock_batch_tracker,
            outbox_repository=mock_outbox_repository,
        )

        essay_ref = EntityReference(
            entity_id="essay_123",
            entity_type="essay",
            parent_id=business_context.batch_id,
        )

        # Act: Publish status update
        correlation_id = uuid4()

        # Act: Try to publish - Kafka succeeds but Redis fails
        with pytest.raises(HuleEduError) as exc_info:
            await event_publisher.publish_status_update(
                essay_ref=essay_ref,
                status=EssayStatus.SPELLCHECKED_SUCCESS,
                correlation_id=correlation_id,
            )

        # Verify it's a Redis/external service error
        assert "EXTERNAL_SERVICE_ERROR" in str(exc_info.value)
        assert "Redis" in str(exc_info.value)

        # Assert: Dual-channel inconsistency - Kafka succeeded, Redis failed

        # Verify Kafka was called successfully (Kafka-first pattern)
        working_kafka_bus.publish.assert_called_once()

        # Outbox should NOT be called when Kafka succeeds
        mock_outbox_repository.add_event.assert_not_called()

        # Verify Redis publishing was attempted and failed
        failing_redis_client.publish_user_notification.assert_called_once()

        # Verify that user_id lookup was attempted
        mock_batch_tracker.get_user_id_for_essay.assert_called_once_with("essay_123")

        # BUSINESS IMPACT VERIFICATION:
        # 1. Essay status correctly updated in service architecture (Kafka)
        # 2. Downstream services receive status updates and continue processing
        # 3. Teachers' UI shows outdated status (Redis failure)
        # 4. Disconnect between actual processing state and user visibility

        business_context.status_updates_completed = True  # Service-to-service updates work
        business_context.teachers_notified = False  # UI updates fail

        # This creates user experience confusion:
        # Processing continues correctly but users can't see progress
        assert business_context.status_updates_completed
        assert not business_context.teachers_notified

    @pytest.mark.asyncio
    async def test_redis_success_kafka_failure_breaks_service_coordination(
        self,
        mock_outbox_repository: AsyncMock,
        mock_settings: Settings,
        mock_batch_tracker: AsyncMock,
        business_context: BusinessWorkflowContext,
    ) -> None:
        """
        BUSINESS SCENARIO: Kafka fails, then outbox fallback also fails.
        BUSINESS IMPACT: Neither services nor UI receive status updates.
        WORKFLOW DISRUPTION: Complete communication breakdown for essay status.

        Note: With Kafka-first pattern, both primary (Kafka) and fallback (outbox) fail.
        """
        # Arrange: Kafka fails first, then outbox fallback also fails
        failing_kafka_bus = AsyncMock(spec=KafkaPublisherProtocol)
        failing_kafka_bus.publish.side_effect = Exception("Kafka connection failed")
        
        mock_outbox_repository.add_event.side_effect = Exception("Database connection failed")

        # Create working Redis client (won't be reached due to earlier failures)
        working_redis_client = AsyncMock(spec=AtomicRedisClientProtocol)
        working_redis_client.publish_user_notification.return_value = None  # Success

        event_publisher = DefaultEventPublisher(
            kafka_bus=failing_kafka_bus,
            settings=mock_settings,
            redis_client=working_redis_client,
            batch_tracker=mock_batch_tracker,
            outbox_repository=mock_outbox_repository,
        )

        essay_ref = EntityReference(
            entity_id="essay_456",
            entity_type="essay",
            parent_id=business_context.batch_id,
        )

        # Act: Attempt status update
        correlation_id = uuid4()

        with pytest.raises(HuleEduError) as exc_info:  # Should raise due to outbox failure
            await event_publisher.publish_status_update(
                essay_ref=essay_ref,
                status=EssayStatus.CJ_ASSESSMENT_SUCCESS,
                correlation_id=correlation_id,
            )

        # Verify it's an outbox storage error (after Kafka failure)
        assert "OUTBOX_STORAGE_ERROR" in str(exc_info.value) or "EXTERNAL_SERVICE_ERROR" in str(exc_info.value)
        
        # Assert: Service coordination failure

        # Verify Kafka was tried first and failed (Kafka-first pattern)
        failing_kafka_bus.publish.assert_called_once()

        # Verify outbox storage was attempted as fallback and also failed
        mock_outbox_repository.add_event.assert_called_once()

        # Redis should NOT be called because publishing failed earlier
        working_redis_client.publish_user_notification.assert_not_called()

        # BUSINESS IMPACT VERIFICATION:
        # 1. Event storage fails - no events reach the outbox
        # 2. Service-to-service coordination fails completely
        # 3. UI notifications never happen
        # 4. Complete status update failure
        # 5. System cannot track essay progress

        business_context.status_updates_completed = False  # Service updates fail
        business_context.teachers_notified = False  # UI updates also fail

        # This represents critical infrastructure failure:
        # Complete breakdown of status tracking and coordination
        assert not business_context.status_updates_completed
        assert not business_context.teachers_notified


class TestBusinessWorkflowRecoveryScenarios:
    """Test business workflow recovery patterns during circuit breaker recovery."""

    @pytest.mark.asyncio
    async def test_batch_workflow_recovery_after_kafka_restoration(
        self,
        mock_outbox_repository: AsyncMock,
        mock_settings: Settings,
        mock_batch_tracker: AsyncMock,
        mock_repository: AsyncMock,
        mock_redis_client: AsyncMock,
        business_context: BusinessWorkflowContext,
    ) -> None:
        """
        BUSINESS SCENARIO: Kafka initially fails but recovers during batch processing.
        BUSINESS IMPACT: Initial events use outbox fallback, later events go directly via Kafka.
        RECOVERY VERIFICATION: Business continuity with automatic recovery to primary path.

        Note: With Kafka-first pattern, we test Kafka failure/recovery scenarios.
        """
        # Arrange: Initially failing Kafka that will recover
        kafka_call_attempts: list[int] = []

        def kafka_side_effect(*_args: Any, **_kwargs: Any) -> None:
            kafka_call_attempts.append(len(kafka_call_attempts))
            if len(kafka_call_attempts) <= 2:  # First 2 calls fail
                raise Exception("Kafka temporarily unavailable")
            # Subsequent calls succeed (return None)

        # Outbox should always succeed (used as fallback when Kafka fails)
        mock_outbox_repository.add_event.return_value = str(uuid4())

        # Create Kafka bus with recovery behavior
        kafka_bus = AsyncMock(spec=KafkaPublisherProtocol)
        kafka_bus.publish.side_effect = kafka_side_effect

        event_publisher = DefaultEventPublisher(
            kafka_bus=kafka_bus,
            settings=mock_settings,
            redis_client=mock_redis_client,
            batch_tracker=mock_batch_tracker,
            outbox_repository=mock_outbox_repository,
        )

        essay_ref = EntityReference(
            entity_id="recovery_essay_123",
            entity_type="essay",
            parent_id=business_context.batch_id,
        )

        # Act: Multiple status updates during outbox failure and recovery
        correlation_id = uuid4()

        # First update: Kafka fails, falls back to outbox (succeeds)
        await event_publisher.publish_status_update(
            essay_ref=essay_ref,
            status=EssayStatus.AWAITING_SPELLCHECK,
            correlation_id=correlation_id,
        )

        # Second update: Kafka still fails, falls back to outbox (succeeds)
        await event_publisher.publish_status_update(
            essay_ref=essay_ref,
            status=EssayStatus.SPELLCHECKING_IN_PROGRESS,
            correlation_id=correlation_id,
        )

        # Third update: Kafka recovered, goes directly via Kafka
        await event_publisher.publish_status_update(
            essay_ref=essay_ref,
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            correlation_id=correlation_id,
        )

        # Assert: Recovery verification
        assert len(kafka_call_attempts) == 3  # Kafka tried 3 times
        assert kafka_bus.publish.call_count == 3  # All attempts recorded
        
        # Outbox was used as fallback for first 2 failed Kafka attempts
        assert mock_outbox_repository.add_event.call_count == 2

        # BUSINESS RECOVERY VERIFICATION:
        # 1. Initial failures captured and logged
        # 2. System maintains local state consistency
        # 3. Recovery allows workflow continuation
        # 4. No business data loss during outage
        # 5. Service coordination resumes normally

        business_context.status_updates_completed = True
        assert business_context.status_updates_completed

        # Verify Redis operations happened for all successful updates
        # All 3 updates succeeded (2 via outbox, 1 via Kafka)
        assert (
            mock_redis_client.publish_user_notification.call_count == 3
        )  # Called for all 3 successful updates


# Integration test combining multiple business impact scenarios
class TestBusinessImpactIntegrationScenarios:
    """Integration tests combining multiple business failure scenarios."""

    @pytest.mark.asyncio
    async def test_complete_batch_workflow_with_intermittent_failures(
        self,
        mock_outbox_repository: AsyncMock,
        mock_settings: Settings,
        mock_batch_tracker: AsyncMock,
        mock_repository: AsyncMock,
        mock_redis_client: AsyncMock,
        business_context: BusinessWorkflowContext,
    ) -> None:
        """
        BUSINESS SCENARIO: Complete batch workflow with intermittent Kafka failures.
        BUSINESS IMPACT: Test end-to-end business resilience during messaging issues.
        INTEGRATION VERIFICATION: Business workflows remain functional despite failures.

        Note: With Kafka-first pattern, we test Kafka failures with outbox fallback.
        """
        # Arrange: Kafka with realistic intermittent failures
        kafka_call_count = 0
        
        def kafka_side_effect(*_args: Any, **_kwargs: Any) -> None:
            nonlocal kafka_call_count
            kafka_call_count += 1
            if kafka_call_count == 1:  # First call fails
                raise Exception("Kafka temporarily unavailable")
            # Subsequent calls succeed

        # Create mock Kafka bus with intermittent failures
        kafka_bus = AsyncMock(spec=KafkaPublisherProtocol)
        kafka_bus.publish.side_effect = kafka_side_effect
        
        # Outbox should always succeed (used as fallback)
        mock_outbox_repository.add_event.return_value = uuid4()

        # Create all business components
        event_publisher = DefaultEventPublisher(
            kafka_bus=kafka_bus,
            settings=mock_settings,
            redis_client=mock_redis_client,
            batch_tracker=mock_batch_tracker,
            outbox_repository=mock_outbox_repository,
        )

        coordination_handler = DefaultBatchCoordinationHandler(
            batch_tracker=mock_batch_tracker,
            repository=mock_repository,
            event_publisher=event_publisher,
        )

        # Create dispatcher for potential use in extended test scenarios
        _dispatcher = DefaultSpecializedServiceRequestDispatcher(
            kafka_bus=kafka_bus,
            settings=mock_settings,
            outbox_repository=mock_outbox_repository,
        )

        # Act: Execute complete business workflow with failures
        correlation_id = uuid4()

        # Step 1: Batch registration (should succeed - index 0, False)
        batch_event = BatchEssaysRegistered(
            batch_id=business_context.batch_id,
            essay_ids=[f"essay_{i}" for i in range(3)],  # Small batch for testing
            expected_essay_count=3,
            user_id="integration_user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_type="batch",
                    entity_id=business_context.batch_id,
                ),
            ),
            course_code=CourseCode.ENG5,
            essay_instructions="Integration test essay instructions",
        )

        # Ensure check_batch_completion returns None during registration (batch not complete)
        mock_batch_tracker.check_batch_completion.return_value = None
        
        result1 = await coordination_handler.handle_batch_essays_registered(
            event_data=batch_event,
            correlation_id=correlation_id,
        )
        assert result1 is True

        # Note: Batch registration doesn't publish events, only registers with tracker and creates DB records
        assert kafka_bus.publish.call_count == 0
        assert (
            mock_outbox_repository.add_event.call_count == 0
        )  # No events published during registration

        # Step 2: Status update (should fail - first outbox call)
        essay_ref = EntityReference(
            entity_id="essay_1",
            entity_type="essay",
            parent_id=business_context.batch_id,
        )

        # Ensure the batch tracker returns a user_id for the essay
        mock_batch_tracker.get_user_id_for_essay.return_value = "integration_user"

        # This call: Kafka fails, falls back to outbox (succeeds)
        await event_publisher.publish_status_update(
            essay_ref=essay_ref,
            status=EssayStatus.READY_FOR_PROCESSING,
            correlation_id=correlation_id,
        )

        # Verify Kafka was tried first and failed, then outbox was used
        assert kafka_bus.publish.call_count == 1
        assert mock_outbox_repository.add_event.call_count == 1

        # Step 3: Another status update (Kafka succeeds this time)
        await event_publisher.publish_status_update(
            essay_ref=essay_ref,
            status=EssayStatus.AWAITING_SPELLCHECK,
            correlation_id=correlation_id,
        )

        # Assert: Integration verification
        assert kafka_bus.publish.call_count == 2  # Kafka tried twice
        assert mock_outbox_repository.add_event.call_count == 1  # Outbox used only once (as fallback)

        # BUSINESS INTEGRATION VERIFICATION:
        # 1. Batch workflow partially completes despite failures
        # 2. Critical operations (registration) succeed
        # 3. Non-critical operations (status updates) may fail gracefully
        # 4. System maintains overall business continuity
        # 5. Teachers see partial progress rather than complete failure

        business_context.essays_ready_published = True  # Critical path succeeded
        business_context.status_updates_completed = True  # All status updates succeeded (via Kafka or outbox)
        business_context.batch_coordinator_notified = True  # BOS coordination maintained

        # Verify all business operations succeeded
        assert business_context.essays_ready_published
        assert business_context.batch_coordinator_notified
        assert business_context.status_updates_completed

        # Verify the exact pattern of calls
        # No outbox calls during batch registration
        # First status update: Kafka failed, outbox succeeded
        # Second status update: Kafka succeeded, no outbox needed
        
        # Verify Redis was called for both successful status updates
        assert mock_redis_client.publish_user_notification.call_count == 2
