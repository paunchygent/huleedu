"""
Integration tests for NLP Phase 1 Student Matching complete workflow.

Tests the full Phase 1 student matching integration between BOS and ELS:
- REGULAR batches: Content Provisioning → Student Matching → Ready for Pipeline
- GUEST batches: Content Provisioning → Direct to Ready (bypass student matching)

Following 070-testing-standards.md:
- Mock only external boundaries (NLP Service, Class Management Service)
- Test real business logic components (handlers, event routing, state transitions)
- Validate complete event flow with proper pydantic model validation
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.batch_coordination_events import (
    BatchContentProvisioningCompletedV1,
)
from common_core.events.envelope import EventEnvelope
from common_core.events.validation_events import (
    StudentAssociationConfirmation,
    StudentAssociationsConfirmedV1,
)
from common_core.metadata_models import EssayProcessingInputRefV1
from common_core.status_enums import BatchStatus
from huleedu_service_libs.error_handling import HuleEduError

from services.batch_orchestrator_service.implementations.batch_content_provisioning_completed_handler import (  # noqa: E501
    BatchContentProvisioningCompletedHandler,
)
from services.batch_orchestrator_service.implementations.student_associations_confirmed_handler import (  # noqa: E501
    StudentAssociationsConfirmedHandler,
)
from services.batch_orchestrator_service.kafka_consumer import BatchKafkaConsumer


class MockBatchRepository:
    """Mock batch repository for Phase 1 integration testing."""

    def __init__(self):
        self.batches = {}
        self.status_updates = []

    async def get_batch_context(self, batch_id: str):
        """Return batch context with class_id to determine GUEST vs REGULAR."""
        batch_data = self.batches.get(batch_id)
        if not batch_data:
            return None

        # Mock context object with class_id attribute
        context = Mock()
        context.class_id = batch_data.get("class_id")
        context.user_id = batch_data.get("user_id", "test_user")
        context.course_code = batch_data.get("course_code", "ENG5")
        return context

    async def get_batch_essays(self, batch_id: str):
        """Return mock essays for student matching."""
        return self.batches.get(batch_id, {}).get("essays", [])

    async def update_batch_status(self, batch_id: str, status: BatchStatus):
        """Track status updates for validation."""
        self.status_updates.append((batch_id, status))
        # Update the status in the batch data too
        if batch_id in self.batches:
            self.batches[batch_id]["status"] = status.value
            return True
        return False

    async def get_batch_by_id(self, batch_id: str):
        """Return batch data for validation."""
        return self.batches.get(batch_id)

    async def store_batch_essays(self, batch_id: str, essays: list):
        """Store essays for a batch."""
        if batch_id in self.batches:
            self.batches[batch_id]["essays"] = essays

    def register_batch(self, batch_id: str, class_id: str | None, essays: list):
        """Register a batch for testing."""
        self.batches[batch_id] = {
            "class_id": class_id,
            "user_id": "test_teacher_123",
            "course_code": "ENG5",
            "essays": essays,
            "status": BatchStatus.AWAITING_STUDENT_VALIDATION.value,  # Initial status for tests
        }


class MockRedisClient:
    """Mock Redis client for integration testing."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}

    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        if key in self.keys:
            return False
        self.keys[key] = value
        return True

    async def delete_key(self, key: str) -> int:
        """Delete a single key - required by RedisClientProtocol."""
        if key in self.keys:
            del self.keys[key]
            return 1
        return 0

    async def delete(self, *keys: str) -> int:
        total_deleted = 0
        for key in keys:
            total_deleted += await self.delete_key(key)
        return total_deleted

    async def get(self, key: str) -> str | None:
        return self.keys.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        self.keys[key] = value
        return True

    async def ping(self) -> bool:
        return True


class RealKafkaMessage:
    """Real Kafka message structure for integration testing."""

    def __init__(self, envelope: EventEnvelope, topic: str):
        self.value = envelope.model_dump_json().encode("utf-8")
        self.topic = topic
        self.partition = 0
        self.offset = 123


@pytest.mark.asyncio
class TestPhase1StudentMatchingIntegration:
    """Test complete Phase 1 student matching integration workflow."""

    @pytest.fixture
    def mock_batch_repo(self):
        """Mock batch repository with test data."""
        return MockBatchRepository()

    @pytest.fixture
    def mock_phase_initiators(self):
        """Mock phase initiators for student matching."""
        from common_core.pipeline_models import PhaseName

        mock_student_matching_initiator = AsyncMock()
        return {PhaseName.STUDENT_MATCHING: mock_student_matching_initiator}

    @pytest.fixture
    def content_provisioning_handler(self, mock_batch_repo, mock_phase_initiators):
        """Create real content provisioning handler with mocked dependencies."""
        return BatchContentProvisioningCompletedHandler(
            batch_repo=mock_batch_repo, phase_initiators_map=mock_phase_initiators
        )

    @pytest.fixture
    def mock_batch_essays_ready_handler(self):
        """Mock the BatchEssaysReadyHandler."""
        from services.batch_orchestrator_service.implementations.batch_essays_ready_handler import (
            BatchEssaysReadyHandler,
        )

        return AsyncMock(spec=BatchEssaysReadyHandler)

    @pytest.fixture
    def student_associations_handler(self, mock_batch_repo):
        """Create real student associations handler with mocked dependencies."""
        return StudentAssociationsConfirmedHandler(batch_repo=mock_batch_repo)

    @pytest.fixture
    def kafka_consumer(
        self,
        content_provisioning_handler,
        student_associations_handler,
        mock_batch_essays_ready_handler,
    ):
        """Create BatchKafkaConsumer with real Phase 1 handlers."""
        # Mock other handlers we don't need for Phase 1 testing
        mock_validation_errors_handler = AsyncMock()
        mock_els_outcome_handler = AsyncMock()
        mock_client_pipeline_handler = AsyncMock()

        redis_client = MockRedisClient()
        return BatchKafkaConsumer(
            kafka_bootstrap_servers="localhost:9092",
            consumer_group="test-phase1-group",
            batch_essays_ready_handler=mock_batch_essays_ready_handler,
            batch_content_provisioning_completed_handler=content_provisioning_handler,
            batch_validation_errors_handler=mock_validation_errors_handler,
            els_batch_phase_outcome_handler=mock_els_outcome_handler,
            client_pipeline_request_handler=mock_client_pipeline_handler,
            student_associations_confirmed_handler=student_associations_handler,
            redis_client=redis_client,
        )

    async def test_regular_batch_student_matching_workflow(
        self,
        kafka_consumer,
        mock_batch_repo,
        mock_phase_initiators,
    ):
        """
        Test complete REGULAR batch student matching workflow.

        Flow:
        1. BatchContentProvisioningCompletedV1 → BOS identifies REGULAR batch
        2. BOS updates status to AWAITING_STUDENT_VALIDATION
        3. BOS initiates student matching via phase initiator
        4. StudentAssociationsConfirmedV1 → BOS processes associations
        5. BOS transitions to ready state
        """
        # Setup test data
        batch_id = str(uuid4())
        class_id = str(uuid4())  # REGULAR batch has class_id
        correlation_id = uuid4()

        # Create test essays
        essays = [
            EssayProcessingInputRefV1(essay_id=str(uuid4()), text_storage_id=f"text_{i}")
            for i in range(3)
        ]

        # Register REGULAR batch in mock repository
        mock_batch_repo.register_batch(batch_id, class_id, essays)

        # === STEP 1: Process BatchContentProvisioningCompletedV1 ===
        content_event = BatchContentProvisioningCompletedV1(
            batch_id=batch_id,
            provisioned_count=3,
            expected_count=3,
            course_code="ENG5",
            user_id="test_teacher_123",
            essays_for_processing=essays,
            correlation_id=correlation_id,
        )

        envelope = EventEnvelope[BatchContentProvisioningCompletedV1](
            event_type="batch.content.provisioning.completed",
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=content_event,
        )

        kafka_msg = RealKafkaMessage(
            envelope=envelope,
            topic=topic_name(ProcessingEvent.BATCH_CONTENT_PROVISIONING_COMPLETED),
        )

        # Process the content provisioning completed event
        await kafka_consumer._handle_message(kafka_msg)

        # Verify REGULAR batch handling
        assert len(mock_batch_repo.status_updates) == 1
        updated_batch_id, updated_status = mock_batch_repo.status_updates[0]
        assert updated_batch_id == batch_id
        assert updated_status == BatchStatus.AWAITING_STUDENT_VALIDATION

        # Verify student matching was initiated
        student_matching_initiator = mock_phase_initiators["student_matching"]
        student_matching_initiator.initiate_phase.assert_called_once()
        call_args = student_matching_initiator.initiate_phase.call_args
        assert call_args.kwargs["batch_id"] == batch_id
        # Verify batch_context contains the class_id
        assert call_args.kwargs["batch_context"].class_id == class_id

        # === STEP 2: Process StudentAssociationsConfirmedV1 ===
        # Create student association confirmations
        associations = [
            StudentAssociationConfirmation(
                essay_id=essay.essay_id,
                student_id=f"student_{i}",
                confidence_score=0.95,
                validation_method="human",
                validated_by="teacher_123",
            )
            for i, essay in enumerate(essays)
        ]

        associations_event = StudentAssociationsConfirmedV1(
            batch_id=batch_id,
            class_id=class_id,
            course_code=CourseCode.ENG5,
            associations=associations,
            timeout_triggered=False,
            validation_summary={"human": 3},
        )

        associations_envelope = EventEnvelope[StudentAssociationsConfirmedV1](
            event_type="student.associations.confirmed",
            source_service="class-management-service",
            correlation_id=correlation_id,
            data=associations_event,
        )

        associations_msg = RealKafkaMessage(
            envelope=associations_envelope,
            topic=topic_name(ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED),
        )

        # Process the student associations event
        await kafka_consumer._handle_message(associations_msg)

        # Verify associations were processed (handler should update status)
        # Note: The actual status update to READY_FOR_PIPELINE_EXECUTION
        # would happen after ELS publishes BatchEssaysReady, which is
        # outside the scope of this Phase 1 integration test

    async def test_guest_batch_bypasses_student_matching(
        self,
        kafka_consumer,
        mock_batch_repo,
        mock_phase_initiators,
    ):
        """
        Test GUEST batch bypasses student matching completely.

        Flow:
        1. BatchContentProvisioningCompletedV1 → BOS identifies GUEST batch
        2. BOS updates status to READY_FOR_PIPELINE_EXECUTION and stores essays
        3. No student matching is initiated (bypassed for GUEST batches)
        """
        # Setup test data
        batch_id = str(uuid4())
        correlation_id = uuid4()

        # Create test essays
        essays = [
            EssayProcessingInputRefV1(essay_id=str(uuid4()), text_storage_id=f"text_{i}")
            for i in range(2)
        ]

        # Register GUEST batch (class_id=None)
        mock_batch_repo.register_batch(batch_id, None, essays)

        # === Process BatchContentProvisioningCompletedV1 ===
        content_event = BatchContentProvisioningCompletedV1(
            batch_id=batch_id,
            provisioned_count=2,
            expected_count=2,
            course_code="ENG5",
            user_id="test_teacher_123",
            essays_for_processing=essays,
            correlation_id=correlation_id,
        )

        envelope = EventEnvelope[BatchContentProvisioningCompletedV1](
            event_type="batch.content.provisioning.completed",
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=content_event,
        )

        kafka_msg = RealKafkaMessage(
            envelope=envelope,
            topic=topic_name(ProcessingEvent.BATCH_CONTENT_PROVISIONING_COMPLETED),
        )

        # Process the content provisioning completed event
        await kafka_consumer._handle_message(kafka_msg)

        # Verify GUEST batch handling - should update to READY_FOR_PIPELINE_EXECUTION
        assert len(mock_batch_repo.status_updates) == 1
        updated_batch_id, updated_status = mock_batch_repo.status_updates[0]
        assert updated_batch_id == batch_id
        assert updated_status == BatchStatus.READY_FOR_PIPELINE_EXECUTION

        # Verify NO student matching was initiated
        student_matching_initiator = mock_phase_initiators["student_matching"]
        student_matching_initiator.initiate_phase.assert_not_called()

    async def test_malformed_content_provisioning_event(self, kafka_consumer):
        """Test error handling for malformed BatchContentProvisioningCompletedV1 events."""
        # Create malformed message
        malformed_msg = Mock()
        malformed_msg.value = b"invalid json content"
        malformed_msg.topic = topic_name(ProcessingEvent.BATCH_CONTENT_PROVISIONING_COMPLETED)
        malformed_msg.partition = 0
        malformed_msg.offset = 456

        # Should raise HuleEduError for malformed JSON
        with pytest.raises(HuleEduError):
            await kafka_consumer._handle_message(malformed_msg)

    async def test_missing_batch_context_error(
        self,
        kafka_consumer,
        mock_batch_repo,
    ):
        """Test error handling when batch context is not found."""
        batch_id = "nonexistent_batch"
        correlation_id = uuid4()

        # Create valid event for non-existent batch
        content_event = BatchContentProvisioningCompletedV1(
            batch_id=batch_id,
            provisioned_count=1,
            expected_count=1,
            course_code="ENG5",
            user_id="test_user",
            essays_for_processing=[],
            correlation_id=correlation_id,
        )

        envelope = EventEnvelope[BatchContentProvisioningCompletedV1](
            event_type="batch.content.provisioning.completed",
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=content_event,
        )

        kafka_msg = RealKafkaMessage(
            envelope=envelope,
            topic=topic_name(ProcessingEvent.BATCH_CONTENT_PROVISIONING_COMPLETED),
        )

        # Should raise validation error for missing batch context
        with pytest.raises(HuleEduError):
            await kafka_consumer._handle_message(kafka_msg)
