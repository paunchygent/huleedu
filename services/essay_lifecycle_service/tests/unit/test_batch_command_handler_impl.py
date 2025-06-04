"""
Unit tests for DefaultBatchCommandHandler.

DefaultBatchCommandHandler processes batch commands from BOS to initiate processing phases
(spellcheck, CJ assessment, etc.) on essays. It transitions essay states via EssayStateMachine
and dispatches requests to specialized services.

Tests cover state transitions, service dispatch, error handling, and metadata updates.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from common_core.batch_service_models import BatchServiceSpellcheckInitiateCommandDataV1
from common_core.enums import EssayStatus
from common_core.metadata_models import EssayProcessingInputRefV1

from services.essay_lifecycle_service.essay_state_machine import CMD_INITIATE_SPELLCHECK
from services.essay_lifecycle_service.implementations.batch_command_handler_impl import (
    DefaultBatchCommandHandler,
)
from services.essay_lifecycle_service.protocols import (
    EssayStateStore,
    EventPublisher,
    SpecializedServiceRequestDispatcher,
)


class TestDefaultBatchCommandHandler:
    """Test suite for DefaultBatchCommandHandler implementation."""

    def create_essay_state_mock(
        self,
        essay_id: str,
        batch_id: str,
        status: EssayStatus = EssayStatus.READY_FOR_PROCESSING,
        commanded_phases: list[str] | None = None
    ) -> MagicMock:
        """Helper to create essay state mocks with consistent structure."""
        essay_state = MagicMock()
        essay_state.essay_id = essay_id
        essay_state.batch_id = batch_id
        essay_state.current_status = status
        essay_state.processing_metadata = {
            "commanded_phases": commanded_phases or []
        }
        return essay_state

    @pytest.fixture
    def mock_state_store(self) -> AsyncMock:
        """Create mock EssayStateStore."""
        return AsyncMock(spec=EssayStateStore)

    @pytest.fixture
    def mock_request_dispatcher(self) -> AsyncMock:
        """Create mock SpecializedServiceRequestDispatcher."""
        return AsyncMock(spec=SpecializedServiceRequestDispatcher)

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock EventPublisher."""
        return AsyncMock(spec=EventPublisher)

    @pytest.fixture
    def command_handler(
        self,
        mock_state_store: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        mock_event_publisher: AsyncMock
    ) -> DefaultBatchCommandHandler:
        """Create DefaultBatchCommandHandler with mocked dependencies."""
        return DefaultBatchCommandHandler(
            state_store=mock_state_store,
            request_dispatcher=mock_request_dispatcher,
            event_publisher=mock_event_publisher
        )

    @pytest.fixture
    def batch_id(self) -> str:
        """Sample batch ID."""
        return "test-batch-123"

    @pytest.fixture
    def correlation_id(self) -> UUID:
        """Sample correlation ID."""
        return uuid4()

    @pytest.fixture
    def essay_id(self) -> str:
        """Sample essay ID."""
        return "test-essay-456"

    @pytest.fixture
    def essay_processing_ref(self, essay_id: str) -> EssayProcessingInputRefV1:
        """Sample essay processing reference."""
        return EssayProcessingInputRefV1(
            essay_id=essay_id,
            text_storage_id="storage-123"
        )

    @pytest.fixture
    def spellcheck_command_data(
        self,
        batch_id: str,
        essay_processing_ref: EssayProcessingInputRefV1
    ) -> BatchServiceSpellcheckInitiateCommandDataV1:
        """Sample spellcheck command data."""
        from common_core.enums import ProcessingEvent
        from common_core.metadata_models import EntityReference

        return BatchServiceSpellcheckInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND,
            entity_ref=EntityReference(entity_id=batch_id, entity_type="batch"),
            essays_to_process=[essay_processing_ref],
            language="en"
        )

    @pytest.fixture
    def sample_essay_state(self, essay_id: str, batch_id: str) -> MagicMock:
        """Sample essay state in READY_FOR_PROCESSING."""
        essay_state = MagicMock()
        essay_state.essay_id = essay_id
        essay_state.batch_id = batch_id
        essay_state.current_status = EssayStatus.READY_FOR_PROCESSING
        essay_state.processing_metadata = {"commanded_phases": []}
        return essay_state

    # Test: process_initiate_spellcheck_command Success Case
    @pytest.mark.asyncio
    async def test_process_initiate_spellcheck_command_success(
        self,
        command_handler: DefaultBatchCommandHandler,
        mock_state_store: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        spellcheck_command_data: BatchServiceSpellcheckInitiateCommandDataV1,
        sample_essay_state: MagicMock,
        correlation_id: UUID,
        essay_id: str,
    ) -> None:
        """Test successful spellcheck command processing with state machine."""
        # Setup mocks
        mock_state_store.get_essay_state.return_value = sample_essay_state
        mock_state_store.update_essay_status_via_machine.return_value = None
        mock_request_dispatcher.dispatch_spellcheck_requests.return_value = None

        with patch('services.essay_lifecycle_service.implementations.batch_command_handler_impl.EssayStateMachine') as mock_state_machine_class:
            mock_machine = MagicMock()
            mock_machine.trigger.return_value = True
            mock_machine.current_status = EssayStatus.AWAITING_SPELLCHECK
            mock_state_machine_class.return_value = mock_machine

            # Execute
            await command_handler.process_initiate_spellcheck_command(
                command_data=spellcheck_command_data,
                correlation_id=correlation_id
            )

            # Verify state store get_essay_state called
            mock_state_store.get_essay_state.assert_called_once_with(essay_id)

            # Verify state machine instantiation
            mock_state_machine_class.assert_called_once_with(
                essay_id=essay_id,
                initial_status=EssayStatus.READY_FOR_PROCESSING
            )

            # Verify state machine trigger
            mock_machine.trigger.assert_called_once_with(CMD_INITIATE_SPELLCHECK)

            # Verify state store update_essay_status_via_machine called with correct parameters
            mock_state_store.update_essay_status_via_machine.assert_called_once_with(
                essay_id,
                EssayStatus.AWAITING_SPELLCHECK,
                {
                    "bos_command": "spellcheck_initiate",
                    "current_phase": "spellcheck",
                    "commanded_phases": ["spellcheck"]
                }
            )

            # Verify request dispatcher called with transitioned essays
            mock_request_dispatcher.dispatch_spellcheck_requests.assert_called_once_with(
                essays_to_process=spellcheck_command_data.essays_to_process,
                language="en",
                correlation_id=correlation_id
            )

    # Test: process_initiate_spellcheck_command State Machine Fails
    @pytest.mark.asyncio
    async def test_process_initiate_spellcheck_command_state_machine_fails(
        self,
        command_handler: DefaultBatchCommandHandler,
        mock_state_store: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        spellcheck_command_data: BatchServiceSpellcheckInitiateCommandDataV1,
        sample_essay_state: MagicMock,
        correlation_id: UUID,
        essay_id: str,
    ) -> None:
        """Test spellcheck command when state machine trigger fails."""
        # Setup mocks
        mock_state_store.get_essay_state.return_value = sample_essay_state

        with patch('services.essay_lifecycle_service.implementations.batch_command_handler_impl.EssayStateMachine') as mock_state_machine_class:
            mock_machine = MagicMock()
            mock_machine.trigger.return_value = False  # State machine fails
            mock_state_machine_class.return_value = mock_machine

            # Execute
            await command_handler.process_initiate_spellcheck_command(
                command_data=spellcheck_command_data,
                correlation_id=correlation_id
            )

            # Verify state machine trigger was attempted
            mock_machine.trigger.assert_called_once_with(CMD_INITIATE_SPELLCHECK)

            # Verify update_essay_status_via_machine was NOT called
            mock_state_store.update_essay_status_via_machine.assert_not_called()

            # Verify request dispatcher was NOT called (no successfully transitioned essays)
            mock_request_dispatcher.dispatch_spellcheck_requests.assert_not_called()

    # Test: process_initiate_spellcheck_command Essay Not Found
    @pytest.mark.asyncio
    async def test_process_initiate_spellcheck_command_essay_not_found(
        self,
        command_handler: DefaultBatchCommandHandler,
        mock_state_store: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        spellcheck_command_data: BatchServiceSpellcheckInitiateCommandDataV1,
        correlation_id: UUID,
        essay_id: str,
    ) -> None:
        """Test spellcheck command when essay is not found in state store."""
        # Setup mock to return None (essay not found)
        mock_state_store.get_essay_state.return_value = None

        # Execute
        await command_handler.process_initiate_spellcheck_command(
            command_data=spellcheck_command_data,
            correlation_id=correlation_id
        )

        # Verify get_essay_state was called
        mock_state_store.get_essay_state.assert_called_once_with(essay_id)

        # Verify update_essay_status_via_machine was NOT called
        mock_state_store.update_essay_status_via_machine.assert_not_called()

        # Verify request dispatcher was NOT called
        mock_request_dispatcher.dispatch_spellcheck_requests.assert_not_called()

    # Test: process_initiate_spellcheck_command Multiple Essays Mixed Success
    @pytest.mark.asyncio
    async def test_process_initiate_spellcheck_command_multiple_essays_mixed_success(
        self,
        command_handler: DefaultBatchCommandHandler,
        mock_state_store: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        batch_id: str,
        correlation_id: UUID,
    ) -> None:
        """Test spellcheck command with multiple essays where some succeed and some fail."""
        from common_core.enums import ProcessingEvent
        from common_core.metadata_models import EntityReference

        # Create multiple essay references
        essay_refs = [
            EssayProcessingInputRefV1(essay_id="essay-1", text_storage_id="storage-1"),
            EssayProcessingInputRefV1(essay_id="essay-2", text_storage_id="storage-2"),
            EssayProcessingInputRefV1(essay_id="essay-3", text_storage_id="storage-3")
        ]

        command_data = BatchServiceSpellcheckInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND,
            entity_ref=EntityReference(entity_id=batch_id, entity_type="batch"),
            essays_to_process=essay_refs,
            language="en"
        )

        # Setup essay states - all found
        essay_states = [
            self.create_essay_state_mock(ref.essay_id, batch_id)
            for ref in essay_refs
        ]

        mock_state_store.get_essay_state.side_effect = essay_states

        with patch(
            'services.essay_lifecycle_service.implementations.batch_command_handler_impl.'
            'EssayStateMachine'
        ) as mock_state_machine_class:
            # Setup state machines - first two succeed, third fails
            mock_machines = []
            for i, _ in enumerate(essay_refs):
                mock_machine = MagicMock()
                mock_machine.trigger.return_value = i < 2  # First two succeed, third fails
                mock_machine.current_status = EssayStatus.AWAITING_SPELLCHECK
                mock_machines.append(mock_machine)

            mock_state_machine_class.side_effect = mock_machines

            # Execute
            await command_handler.process_initiate_spellcheck_command(
                command_data=command_data,
                correlation_id=correlation_id
            )

            # Verify all state machines were created and triggered
            assert mock_state_machine_class.call_count == 3
            for machine in mock_machines:
                machine.trigger.assert_called_once_with(CMD_INITIATE_SPELLCHECK)

            # Verify update_essay_status_via_machine called only for successful transitions (first two)
            assert mock_state_store.update_essay_status_via_machine.call_count == 2

            # Verify request dispatcher called with only successfully transitioned essays
            mock_request_dispatcher.dispatch_spellcheck_requests.assert_called_once()
            args, kwargs = mock_request_dispatcher.dispatch_spellcheck_requests.call_args

            # Should only contain first two essays (successfully transitioned)
            assert len(kwargs['essays_to_process']) == 2
            assert kwargs['essays_to_process'][0].essay_id == "essay-1"
            assert kwargs['essays_to_process'][1].essay_id == "essay-2"

    # Test: process_initiate_spellcheck_command Dispatch Fails
    @pytest.mark.asyncio
    async def test_process_initiate_spellcheck_command_dispatch_fails(
        self,
        command_handler: DefaultBatchCommandHandler,
        mock_state_store: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        spellcheck_command_data: BatchServiceSpellcheckInitiateCommandDataV1,
        sample_essay_state: MagicMock,
        correlation_id: UUID,
    ) -> None:
        """Test spellcheck command when request dispatcher raises exception."""
        # Setup mocks - state transition succeeds but dispatcher fails
        mock_state_store.get_essay_state.return_value = sample_essay_state
        mock_request_dispatcher.dispatch_spellcheck_requests.side_effect = Exception(
            "Dispatch failed"
        )

        with patch(
            'services.essay_lifecycle_service.implementations.batch_command_handler_impl.'
            'EssayStateMachine'
        ) as mock_state_machine_class:
            mock_machine = MagicMock()
            mock_machine.trigger.return_value = True
            mock_machine.current_status = EssayStatus.AWAITING_SPELLCHECK
            mock_state_machine_class.return_value = mock_machine

            # Execute - should not raise exception
            await command_handler.process_initiate_spellcheck_command(
                command_data=spellcheck_command_data,
                correlation_id=correlation_id
            )

            # Verify state transitions still completed successfully
            mock_state_store.update_essay_status_via_machine.assert_called_once()

            # Verify request dispatcher was called (and failed)
            mock_request_dispatcher.dispatch_spellcheck_requests.assert_called_once()

    # Test: Stub Methods
    @pytest.mark.asyncio
    async def test_process_initiate_nlp_command_stub(
        self,
        command_handler: DefaultBatchCommandHandler,
        correlation_id: UUID,
    ) -> None:
        """Test NLP command stub method."""
        # Create mock command data
        from common_core.batch_service_models import BatchServiceNLPInitiateCommandDataV1

        mock_command = MagicMock(spec=BatchServiceNLPInitiateCommandDataV1)

        # Execute - should not raise exception
        await command_handler.process_initiate_nlp_command(
            command_data=mock_command,
            correlation_id=correlation_id
        )

        # Method should complete without error (just logs stub message)

    @pytest.mark.asyncio
    async def test_process_initiate_ai_feedback_command_stub(
        self,
        command_handler: DefaultBatchCommandHandler,
        correlation_id: UUID,
    ) -> None:
        """Test AI feedback command stub method."""
        from common_core.batch_service_models import BatchServiceAIFeedbackInitiateCommandDataV1

        mock_command = MagicMock(spec=BatchServiceAIFeedbackInitiateCommandDataV1)

        # Execute - should not raise exception
        await command_handler.process_initiate_ai_feedback_command(
            command_data=mock_command,
            correlation_id=correlation_id
        )

    @pytest.mark.asyncio
    async def test_process_initiate_cj_assessment_command_stub(
        self,
        command_handler: DefaultBatchCommandHandler,
        correlation_id: UUID,
    ) -> None:
        """Test CJ assessment command stub method."""
        from common_core.batch_service_models import BatchServiceCJAssessmentInitiateCommandDataV1

        mock_command = MagicMock(spec=BatchServiceCJAssessmentInitiateCommandDataV1)

        # Execute - should not raise exception
        await command_handler.process_initiate_cj_assessment_command(
            command_data=mock_command,
            correlation_id=correlation_id
        )

    # Test: Metadata Update
    @pytest.mark.asyncio
    async def test_process_initiate_spellcheck_command_metadata_update(
        self,
        command_handler: DefaultBatchCommandHandler,
        mock_state_store: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        spellcheck_command_data: BatchServiceSpellcheckInitiateCommandDataV1,
        correlation_id: UUID,
        essay_id: str,
        batch_id: str,
    ) -> None:
        """Test that commanded_phases metadata is properly updated."""
        # Create essay state with existing commanded_phases
        essay_state = self.create_essay_state_mock(
            essay_id, batch_id, commanded_phases=["existing_phase"]
        )

        mock_state_store.get_essay_state.return_value = essay_state

        with patch('services.essay_lifecycle_service.implementations.batch_command_handler_impl.EssayStateMachine') as mock_state_machine_class:
            mock_machine = MagicMock()
            mock_machine.trigger.return_value = True
            mock_machine.current_status = EssayStatus.AWAITING_SPELLCHECK
            mock_state_machine_class.return_value = mock_machine

            # Execute
            await command_handler.process_initiate_spellcheck_command(
                command_data=spellcheck_command_data,
                correlation_id=correlation_id
            )

            # Verify metadata update includes current_phase and proper commanded_phases
            mock_state_store.update_essay_status_via_machine.assert_called_once_with(
                essay_id,
                EssayStatus.AWAITING_SPELLCHECK,
                {
                    "bos_command": "spellcheck_initiate",
                    "current_phase": "spellcheck",
                    "commanded_phases": ["spellcheck", "existing_phase"]  # New phase added first (implementation behavior)
                }
            )
