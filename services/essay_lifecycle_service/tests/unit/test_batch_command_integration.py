"""
Integration tests for batch command processing.

Tests the integration between batch command handlers and essay lifecycle components.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.batch_service_models import (
    BatchServiceSpellcheckInitiateCommandDataV1,
    EssayProcessingInputRefV1,
)
from common_core.event_enums import ProcessingEvent
from common_core.metadata_models import EntityReference

from services.essay_lifecycle_service.implementations.batch_command_handler_impl import (
    DefaultBatchCommandHandler,
)


class TestBatchCommandIntegration:
    """Integration tests for batch command processing."""

    @pytest.mark.asyncio
    async def test_command_handler_processes_spellcheck_command(self) -> None:
        """Test that command handler can process a spellcheck command."""
        # Create mocked service handlers
        mock_spellcheck_handler = AsyncMock()
        mock_cj_assessment_handler = AsyncMock()
        mock_future_services_handler = AsyncMock()

        # Create handler with mocked service handlers
        handler = DefaultBatchCommandHandler(
            spellcheck_handler=mock_spellcheck_handler,
            cj_assessment_handler=mock_cj_assessment_handler,
            future_services_handler=mock_future_services_handler,
        )

        # Create simple command
        command_data = BatchServiceSpellcheckInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND,
            entity_ref=EntityReference(entity_id="test-batch", entity_type="batch"),
            essays_to_process=[
                EssayProcessingInputRefV1(essay_id="essay-1", text_storage_id="storage-1")
            ],
            language="en",
        )

        correlation_id = uuid4()

        # Execute
        await handler.process_initiate_spellcheck_command(command_data, correlation_id)

        # Verify delegation to spellcheck handler
        mock_spellcheck_handler.process_initiate_spellcheck_command.assert_called_once_with(
            command_data, correlation_id
        )

        # Verify other handlers not called
        mock_cj_assessment_handler.process_initiate_cj_assessment_command.assert_not_called()
        mock_future_services_handler.process_initiate_nlp_command.assert_not_called()
        mock_future_services_handler.process_initiate_ai_feedback_command.assert_not_called()

    @pytest.mark.asyncio
    async def test_command_handler_handles_missing_essay_gracefully(self) -> None:
        """Test that command handler handles missing essays gracefully."""
        # Create mocked service handlers
        mock_spellcheck_handler = AsyncMock()
        mock_cj_assessment_handler = AsyncMock()
        mock_future_services_handler = AsyncMock()

        # Create handler with mocked service handlers
        handler = DefaultBatchCommandHandler(
            spellcheck_handler=mock_spellcheck_handler,
            cj_assessment_handler=mock_cj_assessment_handler,
            future_services_handler=mock_future_services_handler,
        )

        # Create command for missing essay
        command_data = BatchServiceSpellcheckInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND,
            entity_ref=EntityReference(entity_id="test-batch", entity_type="batch"),
            essays_to_process=[
                EssayProcessingInputRefV1(essay_id="missing-essay", text_storage_id="storage-1")
            ],
            language="en",
        )

        correlation_id = uuid4()

        # Execute - should not raise exception
        await handler.process_initiate_spellcheck_command(command_data, correlation_id)

        # Verify delegation to spellcheck handler
        mock_spellcheck_handler.process_initiate_spellcheck_command.assert_called_once_with(
            command_data, correlation_id
        )
