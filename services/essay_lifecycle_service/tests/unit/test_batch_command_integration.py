"""
Simple integration tests for batch command processing.

Tests that the command handler processes commands correctly without over-mocking.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from common_core.batch_service_models import BatchServiceSpellcheckInitiateCommandDataV1
from common_core.enums import EssayStatus, ProcessingEvent
from common_core.metadata_models import EntityReference, EssayProcessingInputRefV1

from services.essay_lifecycle_service.implementations.batch_command_handler_impl import (
    DefaultBatchCommandHandler,
)


class TestBatchCommandIntegration:
    """Simple tests for command processing - no over-mocking."""

    @pytest.mark.asyncio
    async def test_command_handler_processes_spellcheck_command(self) -> None:
        """Test that command handler can process a spellcheck command."""
        # Simple mocks
        mock_state_store = AsyncMock()
        mock_request_dispatcher = AsyncMock()
        mock_event_publisher = AsyncMock()

        # Create handler
        handler = DefaultBatchCommandHandler(
            repository=mock_state_store,
            request_dispatcher=mock_request_dispatcher,
            event_publisher=mock_event_publisher
        )

        # Create simple command
        command_data = BatchServiceSpellcheckInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND,
            entity_ref=EntityReference(entity_id="test-batch", entity_type="batch"),
            essays_to_process=[
                EssayProcessingInputRefV1(essay_id="essay-1", text_storage_id="storage-1")
            ],
            language="en"
        )

        # Mock essay state
        essay_state = MagicMock()
        essay_state.essay_id = "essay-1"
        essay_state.batch_id = "test-batch"
        essay_state.current_status = EssayStatus.READY_FOR_PROCESSING
        essay_state.processing_metadata = {"commanded_phases": []}
        mock_state_store.get_essay_state.return_value = essay_state

        with patch('services.essay_lifecycle_service.implementations.batch_command_handler_impl.EssayStateMachine') as mock_machine_class:
            mock_machine = MagicMock()
            mock_machine.trigger.return_value = True
            mock_machine.current_status = EssayStatus.AWAITING_SPELLCHECK
            mock_machine_class.return_value = mock_machine

            # Execute - this should not raise an exception
            await handler.process_initiate_spellcheck_command(
                command_data=command_data,
                correlation_id=uuid4()
            )

            # Verify basic functionality
            mock_state_store.get_essay_state.assert_called_with("essay-1")
            mock_machine.trigger.assert_called_with("CMD_INITIATE_SPELLCHECK")
            mock_state_store.update_essay_status_via_machine.assert_called()
            mock_request_dispatcher.dispatch_spellcheck_requests.assert_called()

    @pytest.mark.asyncio
    async def test_command_handler_handles_missing_essay_gracefully(self) -> None:
        """Test that handler gracefully handles missing essays."""
        # Simple mocks
        mock_state_store = AsyncMock()
        mock_request_dispatcher = AsyncMock()
        mock_event_publisher = AsyncMock()

        handler = DefaultBatchCommandHandler(
            repository=mock_state_store,
            request_dispatcher=mock_request_dispatcher,
            event_publisher=mock_event_publisher
        )

        command_data = BatchServiceSpellcheckInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND,
            entity_ref=EntityReference(entity_id="test-batch", entity_type="batch"),
            essays_to_process=[
                EssayProcessingInputRefV1(essay_id="missing-essay", text_storage_id="storage-1")
            ],
            language="en"
        )

        # Mock returns None for missing essay
        mock_state_store.get_essay_state.return_value = None

        # Should not raise exception
        await handler.process_initiate_spellcheck_command(
            command_data=command_data,
            correlation_id=uuid4()
        )

        # Should not attempt state updates or dispatch
        mock_state_store.update_essay_status_via_machine.assert_not_called()
        mock_request_dispatcher.dispatch_spellcheck_requests.assert_not_called()
