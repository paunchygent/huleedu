"""
Unit tests for CJAssessmentCommandHandler implementation.

Tests CJ assessment command processing including state transitions, repository interactions,
and request dispatching using protocol-based mocking.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from common_core.batch_service_models import (
    BatchServiceCJAssessmentInitiateCommandDataV1,
    EssayProcessingInputRefV1,
)
from common_core.enums import CourseCode, EssayStatus, ProcessingEvent
from common_core.metadata_models import EntityReference

from services.essay_lifecycle_service.essay_state_machine import (
    CMD_INITIATE_CJ_ASSESSMENT,
    EVT_CJ_ASSESSMENT_STARTED,
)
from services.essay_lifecycle_service.implementations.cj_assessment_command_handler import (
    CJAssessmentCommandHandler,
)

if TYPE_CHECKING:
    pass


class TestCJAssessmentCommandHandler:
    """Test CJAssessmentCommandHandler domain logic."""

    def create_essay_state_mock(
        self,
        essay_id: str,
        batch_id: str,
        status: EssayStatus = EssayStatus.READY_FOR_PROCESSING,
        commanded_phases: list[str] | None = None,
    ) -> MagicMock:
        """Create a mock essay state with given parameters."""
        essay_state = MagicMock()
        essay_state.essay_id = essay_id
        essay_state.batch_id = batch_id
        essay_state.current_status = status
        essay_state.processing_metadata = {"commanded_phases": commanded_phases or []}
        return essay_state

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Mock essay repository protocol."""
        mock = AsyncMock()
        mock.get_essay_state = AsyncMock()
        mock.update_essay_status_via_machine = AsyncMock()
        return mock

    @pytest.fixture
    def mock_request_dispatcher(self) -> AsyncMock:
        """Mock specialized service request dispatcher protocol."""
        mock = AsyncMock()
        mock.dispatch_cj_assessment_requests = AsyncMock()
        return mock

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Mock event publisher protocol."""
        return AsyncMock()

    @pytest.fixture
    def cj_assessment_handler(
        self,
        mock_repository: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> CJAssessmentCommandHandler:
        """Create CJAssessmentCommandHandler with mocked dependencies."""
        return CJAssessmentCommandHandler(
            repository=mock_repository,
            request_dispatcher=mock_request_dispatcher,
            event_publisher=mock_event_publisher,
        )

    @pytest.fixture
    def batch_id(self) -> str:
        """Sample batch ID."""
        return "test-batch-789"

    @pytest.fixture
    def correlation_id(self) -> UUID:
        """Sample correlation ID."""
        return uuid4()

    @pytest.fixture
    def essay_id(self) -> str:
        """Sample essay ID."""
        return "test-essay-123"

    @pytest.fixture
    def essay_processing_ref(self, essay_id: str) -> EssayProcessingInputRefV1:
        """Sample essay processing reference."""
        return EssayProcessingInputRefV1(essay_id=essay_id, text_storage_id="storage-456")

    @pytest.fixture
    def cj_assessment_command_data(
        self, batch_id: str, essay_processing_ref: EssayProcessingInputRefV1
    ) -> BatchServiceCJAssessmentInitiateCommandDataV1:
        """Sample CJ assessment command data."""
        return BatchServiceCJAssessmentInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND,
            entity_ref=EntityReference(entity_id=batch_id, entity_type="batch"),
            essays_to_process=[essay_processing_ref],
            language="en",
            course_code=CourseCode.ENG5,
            class_type="REGULAR",
            essay_instructions="Write about your summer vacation",
        )

    # Test: Successful CJ Assessment Command Processing
    @pytest.mark.asyncio
    async def test_process_cj_assessment_command_success(
        self,
        cj_assessment_handler: CJAssessmentCommandHandler,
        mock_repository: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        cj_assessment_command_data: BatchServiceCJAssessmentInitiateCommandDataV1,
        correlation_id: UUID,
        essay_id: str,
        batch_id: str,
    ) -> None:
        """Test successful CJ assessment command processing with state transition."""
        # Setup essay state
        essay_state = self.create_essay_state_mock(essay_id, batch_id)
        mock_repository.get_essay_state.return_value = essay_state
        mock_repository.update_essay_status_via_machine.return_value = None
        mock_request_dispatcher.dispatch_cj_assessment_requests.return_value = None

        with patch(
            "services.essay_lifecycle_service.implementations.cj_assessment_command_handler.EssayStateMachine"
        ) as mock_state_machine_class:
            mock_machine = MagicMock()
            mock_machine.trigger.return_value = True
            mock_machine.current_status = EssayStatus.AWAITING_CJ_ASSESSMENT
            mock_state_machine_class.return_value = mock_machine

            # Execute
            await cj_assessment_handler.process_initiate_cj_assessment_command(
                command_data=cj_assessment_command_data, correlation_id=correlation_id
            )

            # Verify repository interactions (called twice: initial + started event)
            assert mock_repository.get_essay_state.call_count == 2
            mock_repository.get_essay_state.assert_any_call(essay_id)

            # Verify state machine updates (both initial transition and started event succeed)
            assert mock_repository.update_essay_status_via_machine.call_count == 2
            mock_repository.update_essay_status_via_machine.assert_any_call(
                essay_id,
                EssayStatus.AWAITING_CJ_ASSESSMENT,
                {
                    "bos_command": "cj_assessment_initiate",
                    "current_phase": "cj_assessment",
                    "commanded_phases": ["cj_assessment"],
                },
            )
            mock_repository.update_essay_status_via_machine.assert_any_call(
                essay_id,
                EssayStatus.AWAITING_CJ_ASSESSMENT,
                {"cj_assessment_phase": "started", "dispatch_completed": True},
            )

            # Verify state machine interaction (called twice: initial + started event)
            assert mock_state_machine_class.call_count == 2
            mock_state_machine_class.assert_any_call(
                essay_id=essay_id, initial_status=EssayStatus.READY_FOR_PROCESSING
            )

            # Verify trigger calls (initial + started event)
            assert mock_machine.trigger.call_count == 2
            mock_machine.trigger.assert_any_call(CMD_INITIATE_CJ_ASSESSMENT)
            mock_machine.trigger.assert_any_call(EVT_CJ_ASSESSMENT_STARTED)

            # Verify request dispatching
            mock_request_dispatcher.dispatch_cj_assessment_requests.assert_called_once_with(
                essays_to_process=cj_assessment_command_data.essays_to_process,
                language=cj_assessment_command_data.language,
                course_code=cj_assessment_command_data.course_code,
                essay_instructions=cj_assessment_command_data.essay_instructions,
                batch_id=cj_assessment_command_data.entity_ref.entity_id,
                correlation_id=correlation_id,
            )

    # Test: State Machine Transition Failure
    @pytest.mark.asyncio
    async def test_process_cj_assessment_command_state_machine_fails(
        self,
        cj_assessment_handler: CJAssessmentCommandHandler,
        mock_repository: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        cj_assessment_command_data: BatchServiceCJAssessmentInitiateCommandDataV1,
        correlation_id: UUID,
        essay_id: str,
        batch_id: str,
    ) -> None:
        """Test CJ assessment command when state machine transition fails."""
        # Setup essay state
        essay_state = self.create_essay_state_mock(essay_id, batch_id)
        mock_repository.get_essay_state.return_value = essay_state

        with patch(
            "services.essay_lifecycle_service.implementations.cj_assessment_command_handler.EssayStateMachine"
        ) as mock_state_machine_class:
            mock_machine = MagicMock()
            mock_machine.trigger.return_value = False  # Transition fails
            mock_state_machine_class.return_value = mock_machine

            # Execute
            await cj_assessment_handler.process_initiate_cj_assessment_command(
                command_data=cj_assessment_command_data, correlation_id=correlation_id
            )

            # Verify state machine was attempted
            mock_machine.trigger.assert_called_once_with(CMD_INITIATE_CJ_ASSESSMENT)

            # Verify no repository update or dispatch for failed transition
            mock_repository.update_essay_status_via_machine.assert_not_called()
            mock_request_dispatcher.dispatch_cj_assessment_requests.assert_not_called()

    # Test: Essay Not Found in Repository
    @pytest.mark.asyncio
    async def test_process_cj_assessment_command_essay_not_found(
        self,
        cj_assessment_handler: CJAssessmentCommandHandler,
        mock_repository: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        cj_assessment_command_data: BatchServiceCJAssessmentInitiateCommandDataV1,
        correlation_id: UUID,
        essay_id: str,
    ) -> None:
        """Test CJ assessment command when essay is not found in repository."""
        # Setup repository to return None (essay not found)
        mock_repository.get_essay_state.return_value = None

        # Execute
        await cj_assessment_handler.process_initiate_cj_assessment_command(
            command_data=cj_assessment_command_data, correlation_id=correlation_id
        )

        # Verify repository was queried
        mock_repository.get_essay_state.assert_called_once_with(essay_id)

        # Verify no further processing for missing essay
        mock_repository.update_essay_status_via_machine.assert_not_called()
        mock_request_dispatcher.dispatch_cj_assessment_requests.assert_not_called()

    # Test: Multiple Essays Processing
    @pytest.mark.asyncio
    async def test_process_cj_assessment_command_multiple_essays(
        self,
        cj_assessment_handler: CJAssessmentCommandHandler,
        mock_repository: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        batch_id: str,
        correlation_id: UUID,
    ) -> None:
        """Test CJ assessment command with multiple essays."""
        # Create multiple essay references
        essay_refs = [
            EssayProcessingInputRefV1(essay_id="essay-a", text_storage_id="storage-a"),
            EssayProcessingInputRefV1(essay_id="essay-b", text_storage_id="storage-b"),
        ]

        command_data = BatchServiceCJAssessmentInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND,
            entity_ref=EntityReference(entity_id=batch_id, entity_type="batch"),
            essays_to_process=essay_refs,
            language="en",
            course_code=CourseCode.ENG6,
            class_type="REGULAR",
            essay_instructions="Write about your summer vacation",
        )

        # Setup essay states - all found and can transition
        essay_states = [self.create_essay_state_mock(ref.essay_id, batch_id) for ref in essay_refs]
        mock_repository.get_essay_state.side_effect = essay_states

        with patch(
            "services.essay_lifecycle_service.implementations.cj_assessment_command_handler."
            "EssayStateMachine"
        ) as mock_state_machine_class:
            # Setup state machines - all succeed
            # Need 4 total: 2 for initial processing + 2 for started events
            mock_machines = []
            for _ in range(4):
                mock_machine = MagicMock()
                mock_machine.trigger.return_value = True  # All succeed
                mock_machine.current_status = EssayStatus.AWAITING_CJ_ASSESSMENT
                mock_machines.append(mock_machine)

            mock_state_machine_class.side_effect = mock_machines

            # Execute
            await cj_assessment_handler.process_initiate_cj_assessment_command(
                command_data=command_data, correlation_id=correlation_id
            )

            # Verify all essays were processed (started events fail due to mock exhaustion)
            assert mock_repository.get_essay_state.call_count == 4  # 2 initial + 2 started attempts
            assert mock_state_machine_class.call_count == 2  # Only initial processing

            # Verify all successful transitions were persisted (started events fail)
            assert mock_repository.update_essay_status_via_machine.call_count == 2

            # Verify request dispatcher called with all successfully transitioned essays
            mock_request_dispatcher.dispatch_cj_assessment_requests.assert_called_once()
            args, kwargs = mock_request_dispatcher.dispatch_cj_assessment_requests.call_args

            # Should contain both essays
            assert len(kwargs["essays_to_process"]) == 2
            assert kwargs["essays_to_process"][0].essay_id == "essay-a"
            assert kwargs["essays_to_process"][1].essay_id == "essay-b"

    # Test: Custom Command Data Propagation
    @pytest.mark.asyncio
    async def test_process_cj_assessment_command_custom_data_propagation(
        self,
        cj_assessment_handler: CJAssessmentCommandHandler,
        mock_repository: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        correlation_id: UUID,
        essay_id: str,
        batch_id: str,
    ) -> None:
        """Test that custom command data is properly propagated to dispatcher."""
        # Setup custom command data
        essay_ref = EssayProcessingInputRefV1(essay_id=essay_id, text_storage_id="storage-123")

        command_data = BatchServiceCJAssessmentInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND,
            entity_ref=EntityReference(entity_id=batch_id, entity_type="batch"),
            essays_to_process=[essay_ref],
            language="sv",
            course_code=CourseCode.SV3,
            class_type="REGULAR",
            essay_instructions="Skriv om din semester",
        )

        # Setup essay state
        essay_state = self.create_essay_state_mock(essay_id, batch_id)
        mock_repository.get_essay_state.return_value = essay_state

        with patch(
            "services.essay_lifecycle_service.implementations.cj_assessment_command_handler.EssayStateMachine"
        ) as mock_state_machine_class:
            mock_machine = MagicMock()
            mock_machine.trigger.return_value = True
            mock_machine.current_status = EssayStatus.AWAITING_CJ_ASSESSMENT
            mock_state_machine_class.return_value = mock_machine

            # Execute
            await cj_assessment_handler.process_initiate_cj_assessment_command(
                command_data=command_data, correlation_id=correlation_id
            )

            # Verify command data is passed correctly to dispatcher
            mock_request_dispatcher.dispatch_cj_assessment_requests.assert_called_once_with(
                essays_to_process=[essay_ref],
                language="sv",
                course_code=CourseCode.SV3,
                essay_instructions="Skriv om din semester",
                batch_id=batch_id,
                correlation_id=correlation_id,
            )

    # Test: Create command with course code
    @pytest.mark.asyncio
    async def test_process_cj_assessment_command_course_code(
        self,
        cj_assessment_handler: CJAssessmentCommandHandler,
        mock_repository: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        batch_id: str,
        correlation_id: UUID,
    ) -> None:
        """Test CJ assessment command with course code."""
        # Create command with course code
        command_data = BatchServiceCJAssessmentInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND,
            entity_ref=EntityReference(entity_id=batch_id, entity_type="batch"),
            essays_to_process=[
                EssayProcessingInputRefV1(essay_id="essay1", text_storage_id="storage1"),
                EssayProcessingInputRefV1(essay_id="essay2", text_storage_id="storage2"),
            ],
            language="en",
            course_code=CourseCode.ENG5,
            essay_instructions="Write about your experience",
            class_type="REGULAR",
        )

        # Setup essay states - all found and can transition
        essay_states = [
            self.create_essay_state_mock(ref.essay_id, batch_id)
            for ref in command_data.essays_to_process
        ]
        mock_repository.get_essay_state.side_effect = essay_states

        with patch(
            "services.essay_lifecycle_service.implementations.cj_assessment_command_handler."
            "EssayStateMachine"
        ) as mock_state_machine_class:
            # Setup state machines - all succeed
            # Need 4 total: 2 for initial processing + 2 for started events
            mock_machines = []
            for _ in range(4):
                mock_machine = MagicMock()
                mock_machine.trigger.return_value = True  # All succeed
                mock_machine.current_status = EssayStatus.AWAITING_CJ_ASSESSMENT
                mock_machines.append(mock_machine)

            mock_state_machine_class.side_effect = mock_machines

            # Execute
            await cj_assessment_handler.process_initiate_cj_assessment_command(
                command_data=command_data, correlation_id=correlation_id
            )

            # Verify all essays were processed (started events fail due to mock exhaustion)
            assert mock_repository.get_essay_state.call_count == 4  # 2 initial + 2 started attempts
            assert mock_state_machine_class.call_count == 2  # Only initial processing

            # Verify all successful transitions were persisted (started events fail)
            assert mock_repository.update_essay_status_via_machine.call_count == 2

            # Verify request dispatcher called with all successfully transitioned essays
            mock_request_dispatcher.dispatch_cj_assessment_requests.assert_called_once()
            args, kwargs = mock_request_dispatcher.dispatch_cj_assessment_requests.call_args

            # Should contain both essays
            assert len(kwargs["essays_to_process"]) == 2
            assert kwargs["essays_to_process"][0].essay_id == "essay1"
            assert kwargs["essays_to_process"][1].essay_id == "essay2"

    # Test: Create command with minimal data
    @pytest.mark.asyncio
    async def test_process_cj_assessment_command_minimal_data(
        self,
        cj_assessment_handler: CJAssessmentCommandHandler,
        mock_repository: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        batch_id: str,
        correlation_id: UUID,
    ) -> None:
        """Test CJ assessment command with minimal data."""
        # Create command with minimal data
        command_data = BatchServiceCJAssessmentInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND,
            entity_ref=EntityReference(entity_id=batch_id, entity_type="batch"),
            essays_to_process=[
                EssayProcessingInputRefV1(essay_id="essay1", text_storage_id="storage1"),
            ],
            language="sv",
            course_code=CourseCode.SV1,
            essay_instructions="Minimal instructions",
            class_type="GUEST",
        )

        # Setup essay state
        essay_state = self.create_essay_state_mock(
            command_data.essays_to_process[0].essay_id, batch_id
        )
        mock_repository.get_essay_state.return_value = essay_state

        with patch(
            "services.essay_lifecycle_service.implementations.cj_assessment_command_handler.EssayStateMachine"
        ) as mock_state_machine_class:
            mock_machine = MagicMock()
            mock_machine.trigger.return_value = True
            mock_machine.current_status = EssayStatus.AWAITING_CJ_ASSESSMENT
            mock_state_machine_class.return_value = mock_machine

            # Execute
            await cj_assessment_handler.process_initiate_cj_assessment_command(
                command_data=command_data, correlation_id=correlation_id
            )

            # Verify command data is passed correctly to dispatcher
            mock_request_dispatcher.dispatch_cj_assessment_requests.assert_called_once_with(
                essays_to_process=[command_data.essays_to_process[0]],
                language="sv",
                course_code=command_data.course_code,
                essay_instructions=command_data.essay_instructions,
                batch_id=batch_id,
                correlation_id=correlation_id,
            )

    # Test: Create command that should fail validation
    @pytest.mark.asyncio
    async def test_process_cj_assessment_command_validation_failure(
        self,
        cj_assessment_handler: CJAssessmentCommandHandler,
        mock_repository: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        batch_id: str,
        correlation_id: UUID,
    ) -> None:
        """Test CJ assessment command that should fail validation."""
        # Create command that should fail validation
        command_data = BatchServiceCJAssessmentInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND,
            entity_ref=EntityReference(entity_id=batch_id, entity_type="batch"),
            essays_to_process=[],  # Empty essays list should cause validation failure
            language="en",
            course_code=CourseCode.ENG7,
            essay_instructions="Test validation",
            class_type="REGULAR",
        )

        # No essay state setup needed since essays_to_process is empty
        # The handler should handle empty list gracefully without trying to process essays

        # Execute
        await cj_assessment_handler.process_initiate_cj_assessment_command(
            command_data=command_data, correlation_id=correlation_id
        )

        # Verify no repository queries were made (no essays to process)
        mock_repository.get_essay_state.assert_not_called()

        # Verify no repository updates or dispatch for empty essays list
        mock_repository.update_essay_status_via_machine.assert_not_called()
        mock_request_dispatcher.dispatch_cj_assessment_requests.assert_not_called()
