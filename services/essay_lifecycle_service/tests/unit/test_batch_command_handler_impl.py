"""
Unit tests for DefaultBatchCommandHandler implementation.

Tests the batch command handler's delegation to service-specific handlers
and proper error handling using protocol-based mocking following Rule 070.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from common_core.batch_service_models import (
    BatchServiceAIFeedbackInitiateCommandDataV1,
    BatchServiceCJAssessmentInitiateCommandDataV1,
    BatchServiceNLPInitiateCommandDataV1,
    BatchServiceSpellcheckInitiateCommandDataV1,
    EssayProcessingInputRefV1,
)
from common_core.status_enums import EssayStatus

from services.essay_lifecycle_service.implementations.batch_command_handler_impl import (
    DefaultBatchCommandHandler,
)

if TYPE_CHECKING:
    pass


class TestDefaultBatchCommandHandler:
    """Test DefaultBatchCommandHandler with mocked service handlers."""

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
    def mock_spellcheck_handler(self) -> AsyncMock:
        """Mock spellcheck command handler."""
        mock = AsyncMock()
        mock.process_initiate_spellcheck_command = AsyncMock()
        return mock

    @pytest.fixture
    def mock_cj_assessment_handler(self) -> AsyncMock:
        """Mock CJ assessment command handler."""
        mock = AsyncMock()
        mock.process_initiate_cj_assessment_command = AsyncMock()
        return mock

    @pytest.fixture
    def mock_future_services_handler(self) -> AsyncMock:
        """Mock future services command handler."""
        mock = AsyncMock()
        mock.process_initiate_nlp_command = AsyncMock()
        mock.process_initiate_ai_feedback_command = AsyncMock()
        return mock

    @pytest.fixture
    def command_handler(
        self,
        mock_spellcheck_handler: AsyncMock,
        mock_cj_assessment_handler: AsyncMock,
        mock_future_services_handler: AsyncMock,
    ) -> DefaultBatchCommandHandler:
        """Create DefaultBatchCommandHandler with mocked service handlers."""
        return DefaultBatchCommandHandler(
            spellcheck_handler=mock_spellcheck_handler,
            cj_assessment_handler=mock_cj_assessment_handler,
            future_services_handler=mock_future_services_handler,
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
        from common_core.event_enums import ProcessingEvent

        return BatchServiceSpellcheckInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND,
            batch_id=batch_id,
            essays_to_process=[essay_processing_ref],
            language="en",
        )

    # Test: process_initiate_spellcheck_command Success Case
    @pytest.mark.asyncio
    async def test_process_initiate_spellcheck_command_success(
        self,
        command_handler: DefaultBatchCommandHandler,
        mock_spellcheck_handler: AsyncMock,
        spellcheck_command_data: BatchServiceSpellcheckInitiateCommandDataV1,
        correlation_id: UUID,
    ) -> None:
        """Test successful spellcheck command delegation."""
        # Execute
        await command_handler.process_initiate_spellcheck_command(
            command_data=spellcheck_command_data, correlation_id=correlation_id
        )

        # Verify delegation to spellcheck handler
        mock_spellcheck_handler.process_initiate_spellcheck_command.assert_called_once_with(
            spellcheck_command_data, correlation_id
        )

    # Test: process_initiate_nlp_command_stub
    @pytest.mark.asyncio
    async def test_process_initiate_nlp_command_stub(
        self,
        command_handler: DefaultBatchCommandHandler,
        mock_future_services_handler: AsyncMock,
        correlation_id: UUID,
    ) -> None:
        """Test NLP command delegation to future services handler."""
        mock_command = MagicMock(spec=BatchServiceNLPInitiateCommandDataV1)

        # Execute
        await command_handler.process_initiate_nlp_command(
            command_data=mock_command, correlation_id=correlation_id
        )

        # Verify delegation to future services handler
        mock_future_services_handler.process_initiate_nlp_command.assert_called_once_with(
            mock_command, correlation_id
        )

    # Test: process_initiate_ai_feedback_command_stub
    @pytest.mark.asyncio
    async def test_process_initiate_ai_feedback_command_stub(
        self,
        command_handler: DefaultBatchCommandHandler,
        mock_future_services_handler: AsyncMock,
        correlation_id: UUID,
    ) -> None:
        """Test AI feedback command delegation to future services handler."""
        mock_command = MagicMock(spec=BatchServiceAIFeedbackInitiateCommandDataV1)

        # Execute
        await command_handler.process_initiate_ai_feedback_command(
            command_data=mock_command, correlation_id=correlation_id
        )

        # Verify delegation to future services handler
        mock_future_services_handler.process_initiate_ai_feedback_command.assert_called_once_with(
            mock_command, correlation_id
        )

    # Test: process_initiate_cj_assessment_command_delegation
    @pytest.mark.asyncio
    async def test_process_initiate_cj_assessment_command_delegation(
        self,
        command_handler: DefaultBatchCommandHandler,
        mock_cj_assessment_handler: AsyncMock,
        correlation_id: UUID,
    ) -> None:
        """Test CJ assessment command delegation to CJ assessment handler."""
        mock_command = MagicMock(spec=BatchServiceCJAssessmentInitiateCommandDataV1)

        # Execute
        await command_handler.process_initiate_cj_assessment_command(
            command_data=mock_command, correlation_id=correlation_id
        )

        # Verify delegation to CJ assessment handler
        mock_cj_assessment_handler.process_initiate_cj_assessment_command.assert_called_once_with(
            mock_command, correlation_id
        )
