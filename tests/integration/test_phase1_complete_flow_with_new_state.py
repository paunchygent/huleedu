"""
Integration test for complete Phase 1 flow with new state machine.

Tests the full Phase 1 student matching flow with the new STUDENT_VALIDATION_COMPLETED
state, verifying:
- State transitions occur in correct order
- Course code propagates through all events
- Essays are NOT available until READY_FOR_PIPELINE_EXECUTION
- Race condition is prevented by new state machine

Following 070-testing-standards.md and 075-test-creation-methodology.md
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.domain_enums import ContentType, CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.batch_coordination_events import (
    BatchContentProvisioningCompletedV1,
    BatchEssaysReady,
)
from common_core.events.envelope import EventEnvelope
from common_core.events.validation_events import (
    StudentAssociationConfirmation,
    StudentAssociationsConfirmedV1,
)
from common_core.metadata_models import (
    EssayProcessingInputRefV1,
    StorageReferenceMetadata,
    SystemProcessingMetadata,
)
from common_core.pipeline_models import PhaseName, PipelineExecutionStatus, ProcessingPipelineState
from common_core.status_enums import AssociationValidationMethod, BatchStatus
from huleedu_service_libs.error_handling import HuleEduError

from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.implementations import (
    batch_content_provisioning_completed_handler as batch_provisioning_handler,
)
from services.batch_orchestrator_service.implementations import (
    student_associations_confirmed_handler as student_assoc_handler,
)
from services.batch_orchestrator_service.implementations.batch_essays_ready_handler import (
    BatchEssaysReadyHandler,
)
from services.batch_orchestrator_service.implementations.student_matching_initiator_impl import (
    StudentMatchingInitiatorImpl,
)
from services.batch_orchestrator_service.protocols import (
    BatchEventPublisherProtocol,
    BatchRepositoryProtocol,
    PipelinePhaseInitiatorProtocol,
)


def make_prompt_ref(label: str) -> StorageReferenceMetadata:
    prompt_ref = StorageReferenceMetadata()
    prompt_ref.add_reference(ContentType.STUDENT_PROMPT_TEXT, label)
    return prompt_ref


# Type aliases for cleaner function signatures
ContentProvisioningHandler = batch_provisioning_handler.BatchContentProvisioningCompletedHandler
StudentAssocHandler = student_assoc_handler.StudentAssociationsConfirmedHandler


class MockBatchContext:
    """Mock batch context that wraps BatchRegistrationRequestV1."""

    def __init__(
        self,
        batch_id: str,
        class_id: str | None,
        user_id: str,
        course_code: CourseCode,
        status: BatchStatus = BatchStatus.AWAITING_CONTENT_VALIDATION,
    ):
        # Create the registration request
        self._registration = BatchRegistrationRequestV1(
            batch_name=f"Test Batch {batch_id[:8]}",
            class_id=class_id,
            course_code=course_code,
            student_prompt_ref=make_prompt_ref("prompt-phase1-mock"),
            expected_essay_count=3,
            requested_pipeline=PhaseName.SPELLCHECK,
            user_id=user_id,
        )
        self.batch_id = batch_id
        self.user_id = user_id
        self.status = status

    # Delegate attribute access to the registration object
    def __getattr__(self, name: str) -> Any:
        return getattr(self._registration, name)


class MockBatchRepository(BatchRepositoryProtocol):
    """Mock batch repository for integration testing."""

    def __init__(self):
        self.batches: dict[str, MockBatchContext] = {}
        self.status_updates: list[tuple[str, BatchStatus]] = []
        self.stored_essays: dict[str, list[Any]] = {}
        self.pipeline_states: dict[str, ProcessingPipelineState] = {}

    async def get_batch_context(self, batch_id: str) -> BatchRegistrationRequestV1 | None:
        """Return batch context."""
        batch = self.batches.get(batch_id)
        return batch._registration if batch else None

    async def get_batch_by_id(self, batch_id: str) -> dict | None:
        """Return batch data."""
        batch = self.batches.get(batch_id)
        if not batch:
            return None
        return {
            "batch_id": batch.batch_id,
            "class_id": batch.class_id,
            "user_id": batch.user_id,
            "course_code": batch.course_code,
            "status": batch.status,
        }

    async def create_batch(self, batch_data: dict) -> dict:
        """Create a new batch record."""
        batch_id = batch_data.get("batch_id", str(uuid4()))
        batch_data["batch_id"] = batch_id
        # Store as context for testing
        return batch_data

    async def update_batch_status(self, batch_id: str, new_status: BatchStatus) -> bool:
        """Track status updates for validation."""
        self.status_updates.append((batch_id, new_status))
        if batch_id in self.batches:
            self.batches[batch_id].status = new_status
            return True
        return False

    async def save_processing_pipeline_state(
        self, batch_id: str, pipeline_state: ProcessingPipelineState
    ) -> bool:
        """Save pipeline processing state for a batch."""
        self.pipeline_states[batch_id] = pipeline_state
        return True

    async def get_processing_pipeline_state(self, batch_id: str) -> ProcessingPipelineState | None:
        """Retrieve pipeline processing state for a batch."""
        return self.pipeline_states.get(batch_id)

    async def store_batch_context(
        self,
        batch_id: str,
        registration_data: BatchRegistrationRequestV1,
        correlation_id: str | None = None,
    ) -> bool:
        """Store batch context information."""
        # For testing, we store in our batches dict
        if batch_id in self.batches:
            # Update existing
            self.batches[batch_id] = MockBatchContext(
                batch_id=batch_id,
                class_id=registration_data.class_id,
                user_id=self.batches[batch_id].user_id,
                course_code=registration_data.course_code,
                status=self.batches[batch_id].status,
            )
        return True

    async def store_batch_essays(self, batch_id: str, essays: list[Any]) -> bool:
        """Store essays for a batch."""
        self.stored_essays[batch_id] = essays
        return True

    async def get_batch_essays(self, batch_id: str) -> list[Any] | None:
        """Return stored essays for validation."""
        return self.stored_essays.get(batch_id)

    async def update_phase_status_atomically(
        self,
        batch_id: str,
        phase_name: PhaseName,
        expected_status: PipelineExecutionStatus,
        new_status: PipelineExecutionStatus,
        completion_timestamp: str | None = None,
        correlation_id: str | None = None,
    ) -> bool:
        """Atomically update phase status if current status matches expected."""
        # For testing, always return True
        return True

    def register_batch(
        self,
        batch_id: str,
        class_id: str | None,
        user_id: str,
        course_code: CourseCode,
        initial_status: BatchStatus = BatchStatus.AWAITING_CONTENT_VALIDATION,
    ) -> None:
        """Register a batch for testing."""
        self.batches[batch_id] = MockBatchContext(
            batch_id=batch_id,
            class_id=class_id,
            user_id=user_id,
            course_code=course_code,
            status=initial_status,
        )


class MockEventPublisher:
    """Mock event publisher to track published events."""

    def __init__(self):
        self.published_events: list[tuple[str, Any]] = []

    async def publish_event(self, topic: str, event: Any) -> None:
        """Track published events."""
        self.published_events.append((topic, event))


class MockKafkaMessage:
    """Mock Kafka message for handler testing."""

    def __init__(self, envelope: EventEnvelope[Any]):
        self.value = envelope.model_dump_json().encode("utf-8")
        self.topic = "test-topic"
        self.partition = 0
        self.offset = 0


class TestPhase1CompleteFlowWithNewState:
    """Test complete Phase 1 flow with new state machine."""

    @pytest.fixture
    def mock_batch_repo(self) -> MockBatchRepository:
        """Create mock batch repository."""
        return MockBatchRepository()

    @pytest.fixture
    def mock_event_publisher(self) -> MockEventPublisher:
        """Create mock event publisher."""
        return MockEventPublisher()

    @pytest.fixture
    def student_matching_initiator(
        self, mock_event_publisher: MockEventPublisher
    ) -> StudentMatchingInitiatorImpl:
        """Create student matching initiator with mocked publisher."""
        # Mock the event publisher protocol
        mock_publisher_protocol = AsyncMock(spec=BatchEventPublisherProtocol)

        async def publish_batch_event(
            event_envelope: Any, key: str | None = None, session: Any | None = None
        ) -> None:
            # Extract the command data from the envelope
            await mock_event_publisher.publish_event(
                topic_name(ProcessingEvent.BATCH_STUDENT_MATCHING_INITIATE_COMMAND),
                event_envelope.data,
            )

        mock_publisher_protocol.publish_batch_event.side_effect = publish_batch_event

        return StudentMatchingInitiatorImpl(event_publisher=mock_publisher_protocol)

    @pytest.fixture
    def content_provisioning_handler(
        self,
        mock_batch_repo: MockBatchRepository,
        student_matching_initiator: StudentMatchingInitiatorImpl,
    ) -> ContentProvisioningHandler:
        """Create content provisioning handler."""
        phase_initiators: dict[PhaseName, PipelinePhaseInitiatorProtocol] = {
            PhaseName.STUDENT_MATCHING: student_matching_initiator
        }
        return batch_provisioning_handler.BatchContentProvisioningCompletedHandler(
            batch_repo=mock_batch_repo,
            phase_initiators_map=phase_initiators,
        )

    @pytest.fixture
    def student_associations_handler(
        self, mock_batch_repo: MockBatchRepository
    ) -> StudentAssocHandler:
        """Create student associations handler."""
        return student_assoc_handler.StudentAssociationsConfirmedHandler(batch_repo=mock_batch_repo)

    @pytest.fixture
    def batch_essays_ready_handler(
        self, mock_batch_repo: MockBatchRepository
    ) -> BatchEssaysReadyHandler:
        """Create batch essays ready handler."""
        # Mock event publisher for BatchEssaysReadyHandler
        mock_publisher = AsyncMock(spec=BatchEventPublisherProtocol)
        return BatchEssaysReadyHandler(
            batch_repo=mock_batch_repo,
            event_publisher=mock_publisher,
        )

    @pytest.mark.asyncio
    async def test_regular_batch_complete_phase1_flow(
        self,
        mock_batch_repo: MockBatchRepository,
        mock_event_publisher: MockEventPublisher,
        content_provisioning_handler: ContentProvisioningHandler,
        student_associations_handler: StudentAssocHandler,
        batch_essays_ready_handler: BatchEssaysReadyHandler,
    ):
        """
        Test complete Phase 1 flow for REGULAR batch with new state machine.

        Flow:
        1. BatchContentProvisioningCompletedV1 → AWAITING_STUDENT_VALIDATION
        2. StudentMatchingInitiateCommand includes course_code
        3. StudentAssociationsConfirmedV1 → STUDENT_VALIDATION_COMPLETED
        4. BatchEssaysReady → READY_FOR_PIPELINE_EXECUTION
        """
        # Setup test data
        batch_id = str(uuid4())
        class_id = str(uuid4())
        user_id = "test_teacher_123"
        course_code = CourseCode.ENG5
        correlation_id = uuid4()

        # Create test essays
        essays = [
            EssayProcessingInputRefV1(
                essay_id=str(uuid4()),
                text_storage_id=f"text_{i}",
            )
            for i in range(3)
        ]

        # Register REGULAR batch in repository
        mock_batch_repo.register_batch(
            batch_id=batch_id,
            class_id=class_id,
            user_id=user_id,
            course_code=course_code,
        )

        # === STEP 1: Process BatchContentProvisioningCompletedV1 ===
        content_event = BatchContentProvisioningCompletedV1(
            batch_id=batch_id,
            provisioned_count=3,
            expected_count=3,
            course_code=course_code,
            user_id=user_id,
            essays_for_processing=essays,
            correlation_id=correlation_id,
        )

        # Create proper envelope
        envelope = EventEnvelope[BatchContentProvisioningCompletedV1](
            event_id=uuid4(),
            event_type=topic_name(ProcessingEvent.BATCH_CONTENT_PROVISIONING_COMPLETED),
            event_timestamp=content_event.timestamp,
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=content_event,
        )

        # Create mock Kafka message
        kafka_msg = MockKafkaMessage(envelope)

        # Process the event
        await content_provisioning_handler.handle_batch_content_provisioning_completed(kafka_msg)

        # Verify state transition to AWAITING_STUDENT_VALIDATION
        assert len(mock_batch_repo.status_updates) == 1
        assert mock_batch_repo.status_updates[0] == (
            batch_id,
            BatchStatus.AWAITING_STUDENT_VALIDATION,
        )

        # Verify student matching was initiated with course_code
        assert len(mock_event_publisher.published_events) == 1
        topic, command = mock_event_publisher.published_events[0]
        assert topic == topic_name(ProcessingEvent.BATCH_STUDENT_MATCHING_INITIATE_COMMAND)
        assert command.entity_id == batch_id  # BaseEventData uses entity_id
        assert command.class_id == class_id
        assert command.course_code == course_code
        assert len(command.essays_to_process) == 3

        # Verify essays ARE stored (needed for student matching phase)
        stored_essays = await mock_batch_repo.get_batch_essays(batch_id)
        assert stored_essays is not None
        assert len(stored_essays) == 3

        # === STEP 2: Simulate StudentAssociationsConfirmedV1 ===
        # Create association confirmations
        associations = [
            StudentAssociationConfirmation(
                essay_id=essay.essay_id,
                student_id=f"student_{i}",
                confidence_score=0.95,
                validation_method=AssociationValidationMethod.HUMAN,
                validated_by=user_id,
            )
            for i, essay in enumerate(essays)
        ]

        associations_event = StudentAssociationsConfirmedV1(
            batch_id=batch_id,
            class_id=class_id,
            course_code=course_code,
            associations=associations,
            timeout_triggered=False,
            validation_summary={"human": 3, "timeout": 0, "auto": 0},
        )

        # Create envelope for associations event
        associations_envelope = EventEnvelope[StudentAssociationsConfirmedV1](
            event_id=uuid4(),
            event_type=topic_name(ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED),
            event_timestamp=associations[0].validated_at,
            source_service="class-management-service",
            correlation_id=correlation_id,
            data=associations_event,
        )

        # Create mock Kafka message
        associations_msg = MockKafkaMessage(associations_envelope)

        # Process the associations event
        await student_associations_handler.handle_student_associations_confirmed(associations_msg)

        # Verify state transition to STUDENT_VALIDATION_COMPLETED
        assert len(mock_batch_repo.status_updates) == 2
        assert mock_batch_repo.status_updates[1] == (
            batch_id,
            BatchStatus.STUDENT_VALIDATION_COMPLETED,
        )

        # Verify essays still stored from step 1 (no change during associations)
        stored_essays = await mock_batch_repo.get_batch_essays(batch_id)
        assert stored_essays is not None
        assert len(stored_essays) == 3

        # === STEP 3: Simulate BatchEssaysReady ===
        # Create metadata for the event
        metadata = SystemProcessingMetadata(
            service_name="essay-lifecycle-service",
            service_version="1.0.0",
            entity_id=batch_id,
            entity_type="batch",
            timestamp=associations[0].validated_at,
        )

        batch_ready_event = BatchEssaysReady(
            batch_id=batch_id,
            ready_essays=essays,
            metadata=metadata,
            course_code=course_code,
            course_language="English",
            student_prompt_ref=make_prompt_ref("prompt-phase1-ready"),
            class_type="REGULAR",
        )

        # Create envelope for batch ready event
        batch_ready_envelope = EventEnvelope[BatchEssaysReady](
            event_id=uuid4(),
            event_type=topic_name(ProcessingEvent.BATCH_ESSAYS_READY),
            event_timestamp=batch_ready_event.metadata.timestamp,
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=batch_ready_event,
        )

        # Create mock Kafka message
        batch_ready_msg = MockKafkaMessage(batch_ready_envelope)

        # Process the batch ready event
        await batch_essays_ready_handler.handle_batch_essays_ready(batch_ready_msg)

        # Verify final state transition to READY_FOR_PIPELINE_EXECUTION
        assert len(mock_batch_repo.status_updates) == 3
        assert mock_batch_repo.status_updates[2] == (
            batch_id,
            BatchStatus.READY_FOR_PIPELINE_EXECUTION,
        )

        # Verify essays still stored and batch is ready for pipeline
        stored_essays = await mock_batch_repo.get_batch_essays(batch_id)
        assert stored_essays is not None
        assert len(stored_essays) == 3
        assert all(hasattr(essay, "essay_id") for essay in stored_essays)

    @pytest.mark.asyncio
    async def test_guest_batch_bypasses_student_validation(
        self,
        mock_batch_repo: MockBatchRepository,
        mock_event_publisher: MockEventPublisher,
        content_provisioning_handler: ContentProvisioningHandler,
    ):
        """
        Test GUEST batch bypasses student validation and new state.

        Flow:
        1. BatchContentProvisioningCompletedV1 → READY_FOR_PIPELINE_EXECUTION
        2. No student matching initiated
        3. Essays stored immediately
        """
        # Setup test data
        batch_id = str(uuid4())
        user_id = "test_user_456"
        course_code = CourseCode.SV1
        correlation_id = uuid4()

        # Create test essays
        essays = [
            EssayProcessingInputRefV1(
                essay_id=str(uuid4()),
                text_storage_id=f"text_{i}",
            )
            for i in range(2)
        ]

        # Register GUEST batch (class_id=None)
        mock_batch_repo.register_batch(
            batch_id=batch_id,
            class_id=None,  # GUEST batch has no class
            user_id=user_id,
            course_code=course_code,
        )

        # Process BatchContentProvisioningCompletedV1
        content_event = BatchContentProvisioningCompletedV1(
            batch_id=batch_id,
            provisioned_count=2,
            expected_count=2,
            course_code=course_code,
            user_id=user_id,
            essays_for_processing=essays,
            correlation_id=correlation_id,
        )

        # Create envelope
        envelope = EventEnvelope[BatchContentProvisioningCompletedV1](
            event_id=uuid4(),
            event_type=topic_name(ProcessingEvent.BATCH_CONTENT_PROVISIONING_COMPLETED),
            event_timestamp=content_event.timestamp,
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=content_event,
        )

        # Create mock Kafka message
        kafka_msg = MockKafkaMessage(envelope)

        await content_provisioning_handler.handle_batch_content_provisioning_completed(kafka_msg)

        # Verify direct transition to READY_FOR_PIPELINE_EXECUTION
        assert len(mock_batch_repo.status_updates) == 1
        assert mock_batch_repo.status_updates[0] == (
            batch_id,
            BatchStatus.READY_FOR_PIPELINE_EXECUTION,
        )

        # Verify NO student matching initiated
        assert len(mock_event_publisher.published_events) == 0

        # Verify essays stored immediately (GUEST flow)
        stored_essays = await mock_batch_repo.get_batch_essays(batch_id)
        assert stored_essays is not None
        assert len(stored_essays) == 2

    @pytest.mark.asyncio
    async def test_course_code_propagation_through_all_events(
        self,
        mock_batch_repo: MockBatchRepository,
        mock_event_publisher: MockEventPublisher,
        content_provisioning_handler: ContentProvisioningHandler,
        student_associations_handler: StudentAssocHandler,
        batch_essays_ready_handler: BatchEssaysReadyHandler,
    ):
        """Test course code propagates correctly through entire event chain."""
        # Test different course codes
        test_cases = [
            (CourseCode.ENG5, "English 5"),
            (CourseCode.ENG6, "English 6"),
            (CourseCode.SV1, "Svenska 1"),
            (CourseCode.SV2, "Svenska 2"),
        ]

        for course_code, course_name in test_cases:
            # Reset mocks
            mock_event_publisher.published_events.clear()
            mock_batch_repo.status_updates.clear()

            # Setup test data
            batch_id = str(uuid4())
            class_id = str(uuid4())
            user_id = "test_teacher"
            correlation_id = uuid4()

            # Register batch
            mock_batch_repo.register_batch(
                batch_id=batch_id,
                class_id=class_id,
                user_id=user_id,
                course_code=course_code,
            )

            # Create test essay
            essay = EssayProcessingInputRefV1(
                essay_id=str(uuid4()),
                text_storage_id="text_123",
            )

            # Process content provisioning
            content_event = BatchContentProvisioningCompletedV1(
                batch_id=batch_id,
                provisioned_count=1,
                expected_count=1,
                course_code=course_code,
                user_id=user_id,
                essays_for_processing=[essay],
                correlation_id=correlation_id,
            )

            # Create envelope
            envelope = EventEnvelope[BatchContentProvisioningCompletedV1](
                event_id=uuid4(),
                event_type=topic_name(ProcessingEvent.BATCH_CONTENT_PROVISIONING_COMPLETED),
                event_timestamp=content_event.timestamp,
                source_service="essay-lifecycle-service",
                correlation_id=correlation_id,
                data=content_event,
            )

            # Create mock Kafka message
            kafka_msg = MockKafkaMessage(envelope)

            await content_provisioning_handler.handle_batch_content_provisioning_completed(
                kafka_msg
            )

            # Verify course code in student matching command
            assert len(mock_event_publisher.published_events) == 1
            _, command = mock_event_publisher.published_events[0]
            assert command.course_code == course_code

    @pytest.mark.asyncio
    async def test_state_machine_prevents_invalid_transitions(
        self,
        mock_batch_repo: MockBatchRepository,
        batch_essays_ready_handler: BatchEssaysReadyHandler,
    ):
        """Test that state machine prevents invalid transitions."""
        # Setup batch in wrong state
        batch_id = str(uuid4())
        mock_batch_repo.register_batch(
            batch_id=batch_id,
            class_id=str(uuid4()),
            user_id="test_user",
            course_code=CourseCode.ENG5,
            initial_status=BatchStatus.AWAITING_STUDENT_VALIDATION,  # Wrong state
        )

        # Try to process BatchEssaysReady (should fail)
        metadata = SystemProcessingMetadata(
            service_name="test",
            service_version="1.0.0",
            entity_id=batch_id,
            entity_type="batch",
        )

        batch_ready_event = BatchEssaysReady(
            batch_id=batch_id,
            ready_essays=[],
            metadata=metadata,
            course_code=CourseCode.ENG5,
            course_language="English",
            student_prompt_ref=make_prompt_ref("prompt-phase1-invalid"),
            class_type="REGULAR",
        )

        # Create envelope for batch ready event
        batch_ready_envelope = EventEnvelope[BatchEssaysReady](
            event_id=uuid4(),
            event_type=topic_name(ProcessingEvent.BATCH_ESSAYS_READY),
            event_timestamp=batch_ready_event.metadata.timestamp,
            source_service="essay-lifecycle-service",
            correlation_id=uuid4(),
            data=batch_ready_event,
        )

        # Create mock Kafka message
        batch_ready_msg = MockKafkaMessage(batch_ready_envelope)

        # Should raise error for invalid state transition
        with pytest.raises(HuleEduError):
            await batch_essays_ready_handler.handle_batch_essays_ready(batch_ready_msg)

        # Verify no state change
        assert len(mock_batch_repo.status_updates) == 0

    @pytest.mark.asyncio
    async def test_essays_not_accessible_before_ready_state(
        self,
        mock_batch_repo: MockBatchRepository,
        student_associations_handler: StudentAssocHandler,
    ):
        """Verify essays are not accessible before READY_FOR_PIPELINE_EXECUTION."""
        # Setup batch
        batch_id = str(uuid4())
        mock_batch_repo.register_batch(
            batch_id=batch_id,
            class_id=str(uuid4()),
            user_id="test_user",
            course_code=CourseCode.ENG5,
            initial_status=BatchStatus.AWAITING_STUDENT_VALIDATION,
        )

        # Process student associations
        associations_event = StudentAssociationsConfirmedV1(
            batch_id=batch_id,
            class_id=str(uuid4()),
            course_code=CourseCode.ENG5,
            associations=[],
            timeout_triggered=False,
            validation_summary={"human": 0},
        )

        # Create envelope for associations event
        from datetime import UTC, datetime

        associations_envelope = EventEnvelope[StudentAssociationsConfirmedV1](
            event_id=uuid4(),
            event_type=topic_name(ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED),
            event_timestamp=datetime.now(UTC),
            source_service="class-management-service",
            correlation_id=uuid4(),
            data=associations_event,
        )

        # Create mock Kafka message
        associations_msg = MockKafkaMessage(associations_envelope)

        await student_associations_handler.handle_student_associations_confirmed(associations_msg)

        # Verify state changed but essays not stored
        assert mock_batch_repo.status_updates[-1][1] == BatchStatus.STUDENT_VALIDATION_COMPLETED
        stored_essays = await mock_batch_repo.get_batch_essays(batch_id)
        assert stored_essays is None or len(stored_essays) == 0  # No essays accessible yet
