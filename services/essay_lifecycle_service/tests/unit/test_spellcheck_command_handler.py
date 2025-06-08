"""
Unit tests for SpellcheckCommandHandler implementation.

Tests spellcheck command processing including state transitions, repository interactions,
and request dispatching using protocol-based mocking.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from common_core.batch_service_models import (
    BatchServiceSpellcheckInitiateCommandDataV1,
    EssayProcessingInputRefV1,
)
from common_core.enums import EssayStatus, ProcessingEvent
from common_core.metadata_models import EntityReference

from services.essay_lifecycle_service.essay_state_machine import (
    CMD_INITIATE_SPELLCHECK,
    EVT_SPELLCHECK_STARTED,
)
from services.essay_lifecycle_service.implementations.spellcheck_command_handler import (
    SpellcheckCommandHandler,
)

if TYPE_CHECKING:
    pass


class TestSpellcheckCommandHandler:
    """Test SpellcheckCommandHandler domain logic."""

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
        mock.dispatch_spellcheck_requests = AsyncMock()
        return mock

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Mock event publisher protocol."""
        return AsyncMock()

    @pytest.fixture
    def spellcheck_handler(
        self,
        mock_repository: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> SpellcheckCommandHandler:
        """Create SpellcheckCommandHandler with mocked dependencies."""
        return SpellcheckCommandHandler(
            repository=mock_repository,
            request_dispatcher=mock_request_dispatcher,
            event_publisher=mock_event_publisher,
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
        return EssayProcessingInputRefV1(essay_id=essay_id, text_storage_id="storage-123")

    @pytest.fixture
    def spellcheck_command_data(
        self, batch_id: str, essay_processing_ref: EssayProcessingInputRefV1
    ) -> BatchServiceSpellcheckInitiateCommandDataV1:
        """Sample spellcheck command data."""
        return BatchServiceSpellcheckInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND,
            entity_ref=EntityReference(entity_id=batch_id, entity_type="batch"),
            essays_to_process=[essay_processing_ref],
            language="en",
        )

    # Test: Successful Spellcheck Command Processing
    @pytest.mark.asyncio
    async def test_process_spellcheck_command_success(
        self,
        spellcheck_handler: SpellcheckCommandHandler,
        mock_repository: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        spellcheck_command_data: BatchServiceSpellcheckInitiateCommandDataV1,
        correlation_id: UUID,
        essay_id: str,
        batch_id: str,
    ) -> None:
        """Test successful spellcheck command processing with state transition."""
        # Setup essay state
        essay_state = self.create_essay_state_mock(essay_id, batch_id)
        mock_repository.get_essay_state.return_value = essay_state
        mock_repository.update_essay_status_via_machine.return_value = None
        mock_request_dispatcher.dispatch_spellcheck_requests.return_value = None

        with patch(
            "services.essay_lifecycle_service.implementations.spellcheck_command_handler.EssayStateMachine"
        ) as mock_state_machine_class:
            mock_machine = MagicMock()
            mock_machine.trigger.return_value = True
            mock_machine.current_status = EssayStatus.AWAITING_SPELLCHECK
            mock_state_machine_class.return_value = mock_machine

            # Execute
            await spellcheck_handler.process_initiate_spellcheck_command(
                command_data=spellcheck_command_data, correlation_id=correlation_id
            )

            # Verify repository interactions (called twice: initial + started event)
            assert mock_repository.get_essay_state.call_count == 2
            mock_repository.get_essay_state.assert_any_call(essay_id)

            # Verify state machine updates (both initial transition and started event succeed)
            assert mock_repository.update_essay_status_via_machine.call_count == 2
            mock_repository.update_essay_status_via_machine.assert_any_call(
                essay_id,
                EssayStatus.AWAITING_SPELLCHECK,
                {
                    "bos_command": "spellcheck_initiate",
                    "current_phase": "spellcheck",
                    "commanded_phases": ["spellcheck"],
                },
            )
            mock_repository.update_essay_status_via_machine.assert_any_call(
                essay_id,
                EssayStatus.AWAITING_SPELLCHECK,
                {"spellcheck_phase": "started", "dispatch_completed": True},
            )

            # Verify state machine interaction (called twice: initial + started event)
            assert mock_state_machine_class.call_count == 2
            mock_state_machine_class.assert_any_call(
                essay_id=essay_id, initial_status=EssayStatus.READY_FOR_PROCESSING
            )

            # Verify trigger calls (initial + started event)
            assert mock_machine.trigger.call_count == 2
            mock_machine.trigger.assert_any_call(CMD_INITIATE_SPELLCHECK)
            mock_machine.trigger.assert_any_call(EVT_SPELLCHECK_STARTED)

            # Verify request dispatching
            mock_request_dispatcher.dispatch_spellcheck_requests.assert_called_once_with(
                essays_to_process=spellcheck_command_data.essays_to_process,
                language="en",
                correlation_id=correlation_id,
            )

    # Test: State Machine Transition Failure
    @pytest.mark.asyncio
    async def test_process_spellcheck_command_state_machine_fails(
        self,
        spellcheck_handler: SpellcheckCommandHandler,
        mock_repository: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        spellcheck_command_data: BatchServiceSpellcheckInitiateCommandDataV1,
        correlation_id: UUID,
        essay_id: str,
        batch_id: str,
    ) -> None:
        """Test spellcheck command when state machine transition fails."""
        # Setup essay state
        essay_state = self.create_essay_state_mock(essay_id, batch_id)
        mock_repository.get_essay_state.return_value = essay_state

        with patch(
            "services.essay_lifecycle_service.implementations.spellcheck_command_handler.EssayStateMachine"
        ) as mock_state_machine_class:
            mock_machine = MagicMock()
            mock_machine.trigger.return_value = False  # Transition fails
            mock_state_machine_class.return_value = mock_machine

            # Execute
            await spellcheck_handler.process_initiate_spellcheck_command(
                command_data=spellcheck_command_data, correlation_id=correlation_id
            )

            # Verify state machine was attempted
            mock_machine.trigger.assert_called_once_with(CMD_INITIATE_SPELLCHECK)

            # Verify no repository update or dispatch for failed transition
            mock_repository.update_essay_status_via_machine.assert_not_called()
            mock_request_dispatcher.dispatch_spellcheck_requests.assert_not_called()

    # Test: Essay Not Found in Repository
    @pytest.mark.asyncio
    async def test_process_spellcheck_command_essay_not_found(
        self,
        spellcheck_handler: SpellcheckCommandHandler,
        mock_repository: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        spellcheck_command_data: BatchServiceSpellcheckInitiateCommandDataV1,
        correlation_id: UUID,
        essay_id: str,
    ) -> None:
        """Test spellcheck command when essay is not found in repository."""
        # Setup repository to return None (essay not found)
        mock_repository.get_essay_state.return_value = None

        # Execute
        await spellcheck_handler.process_initiate_spellcheck_command(
            command_data=spellcheck_command_data, correlation_id=correlation_id
        )

        # Verify repository was queried
        mock_repository.get_essay_state.assert_called_once_with(essay_id)

        # Verify no further processing for missing essay
        mock_repository.update_essay_status_via_machine.assert_not_called()
        mock_request_dispatcher.dispatch_spellcheck_requests.assert_not_called()

    # Test: Multiple Essays with Mixed Results
    @pytest.mark.asyncio
    async def test_process_spellcheck_command_multiple_essays_mixed_success(
        self,
        spellcheck_handler: SpellcheckCommandHandler,
        mock_repository: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        batch_id: str,
        correlation_id: UUID,
    ) -> None:
        """Test spellcheck command with multiple essays where some succeed and some fail."""
        # Create multiple essay references
        essay_refs = [
            EssayProcessingInputRefV1(essay_id="essay-1", text_storage_id="storage-1"),
            EssayProcessingInputRefV1(essay_id="essay-2", text_storage_id="storage-2"),
            EssayProcessingInputRefV1(essay_id="essay-3", text_storage_id="storage-3"),
        ]

        command_data = BatchServiceSpellcheckInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND,
            entity_ref=EntityReference(entity_id=batch_id, entity_type="batch"),
            essays_to_process=essay_refs,
            language="en",
        )

        # Setup essay states - all found
        essay_states = [self.create_essay_state_mock(ref.essay_id, batch_id) for ref in essay_refs]
        mock_repository.get_essay_state.side_effect = essay_states

        with patch(
            "services.essay_lifecycle_service.implementations.spellcheck_command_handler."
            "EssayStateMachine"
        ) as mock_state_machine_class:
            # Setup state machines - first two succeed, third fails
            # Need 5 total: 3 for initial processing + 2 for started events (only successful ones)
            mock_machines = []
            for i in range(5):
                mock_machine = MagicMock()
                if i < 3:  # Initial processing: first two succeed, third fails
                    mock_machine.trigger.return_value = i < 2
                else:  # Started events: both succeed
                    mock_machine.trigger.return_value = True
                mock_machine.current_status = EssayStatus.AWAITING_SPELLCHECK
                mock_machines.append(mock_machine)

            mock_state_machine_class.side_effect = mock_machines

            # Execute
            await spellcheck_handler.process_initiate_spellcheck_command(
                command_data=command_data, correlation_id=correlation_id
            )

            # Verify all essays were processed (started events fail due to mock exhaustion)
            assert mock_repository.get_essay_state.call_count == 5  # 3 initial + 2 started attempts
            assert mock_state_machine_class.call_count == 3  # Only initial processing

            # Verify only successful transitions were persisted (started events fail)
            assert mock_repository.update_essay_status_via_machine.call_count == 2

            # Verify request dispatcher called with successfully transitioned essays only
            mock_request_dispatcher.dispatch_spellcheck_requests.assert_called_once()
            args, kwargs = mock_request_dispatcher.dispatch_spellcheck_requests.call_args

            # Should only contain first two essays (successfully transitioned)
            assert len(kwargs["essays_to_process"]) == 2
            assert kwargs["essays_to_process"][0].essay_id == "essay-1"
            assert kwargs["essays_to_process"][1].essay_id == "essay-2"

    # Test: Metadata Update with Existing Phases
    @pytest.mark.asyncio
    async def test_process_spellcheck_command_metadata_preserves_existing_phases(
        self,
        spellcheck_handler: SpellcheckCommandHandler,
        mock_repository: AsyncMock,
        mock_request_dispatcher: AsyncMock,
        spellcheck_command_data: BatchServiceSpellcheckInitiateCommandDataV1,
        correlation_id: UUID,
        essay_id: str,
        batch_id: str,
    ) -> None:
        """Test that existing commanded_phases are preserved when adding spellcheck."""
        # Setup essay state with existing phases
        essay_state = self.create_essay_state_mock(
            essay_id, batch_id, commanded_phases=["existing_phase"]
        )
        mock_repository.get_essay_state.return_value = essay_state

        with patch(
            "services.essay_lifecycle_service.implementations.spellcheck_command_handler.EssayStateMachine"
        ) as mock_state_machine_class:
            mock_machine = MagicMock()
            mock_machine.trigger.return_value = True
            mock_machine.current_status = EssayStatus.AWAITING_SPELLCHECK
            mock_state_machine_class.return_value = mock_machine

            # Execute
            await spellcheck_handler.process_initiate_spellcheck_command(
                command_data=spellcheck_command_data, correlation_id=correlation_id
            )

            # Verify metadata includes both existing and new phases (called twice: transition + started event)
            assert mock_repository.update_essay_status_via_machine.call_count == 2

            # Check the first call (initial transition) has the correct metadata
            first_call_args = mock_repository.update_essay_status_via_machine.call_args_list[0]
            metadata = first_call_args.args[2]

            assert metadata["bos_command"] == "spellcheck_initiate"
            assert metadata["current_phase"] == "spellcheck"
            assert "existing_phase" in metadata["commanded_phases"]
            assert "spellcheck" in metadata["commanded_phases"]
            assert len(metadata["commanded_phases"]) == 2
