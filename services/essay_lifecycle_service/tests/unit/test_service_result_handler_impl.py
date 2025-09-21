"""
Unit tests for DefaultServiceResultHandler implementation.

Tests the service result handler's integration with EssayStateMachine
and batch phase coordination for Task 2.2.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.event_enums import ProcessingEvent
from common_core.events.spellcheck_models import SpellcheckMetricsV1, SpellcheckResultV1
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import EssayStatus

from services.essay_lifecycle_service.implementations.service_result_handler_impl import (
    DefaultServiceResultHandler,
)
from services.essay_lifecycle_service.protocols import (
    BatchPhaseCoordinator,
    EssayRepositoryProtocol,
)


class TestDefaultServiceResultHandler:
    """Test suite for DefaultServiceResultHandler."""

    @pytest.fixture
    def mock_essay_repository(self) -> AsyncMock:
        """Mock EssayRepositoryProtocol for testing using protocol-based mocking."""
        return AsyncMock(spec=EssayRepositoryProtocol)

    @pytest.fixture
    def mock_batch_coordinator(self) -> AsyncMock:
        """Mock BatchPhaseCoordinator for testing using protocol-based mocking."""
        return AsyncMock(spec=BatchPhaseCoordinator)

    # Using shared mock_session_factory fixture from test_utils

    @pytest.fixture
    def handler(
        self,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_session_factory: AsyncMock,
    ) -> DefaultServiceResultHandler:
        """Create DefaultServiceResultHandler instance for testing."""
        return DefaultServiceResultHandler(
            repository=mock_essay_repository,
            batch_coordinator=mock_batch_coordinator,
            session_factory=mock_session_factory,
        )

    @pytest.fixture
    def mock_essay_state(self) -> MagicMock:
        """Create mock EssayState for testing."""
        essay_state = MagicMock()
        essay_state.essay_id = "test-essay-1"
        essay_state.current_status = EssayStatus.SPELLCHECKING_IN_PROGRESS
        essay_state.batch_id = "test-batch-1"
        essay_state.processing_metadata = {
            "current_phase": "spellcheck",
            "commanded_phases": ["spellcheck"],
        }
        return essay_state

    async def test_handle_spellcheck_rich_result_updates_metrics(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
    ) -> None:
        """Rich spellcheck event should persist correction metrics in metadata."""

        correlation_id = uuid4()

        existing_state = MagicMock()
        existing_state.processing_metadata = {
            "spellcheck_result": {
                "success": True,
                "status": EssayStatus.SPELLCHECKED_SUCCESS.value,
                "corrected_text_storage_id": "corrected-456",
            }
        }
        mock_essay_repository.get_essay_state.return_value = existing_state

        metrics = SpellcheckMetricsV1(
            total_corrections=4,
            l2_dictionary_corrections=1,
            spellchecker_corrections=3,
            word_count=200,
            correction_density=2.0,
        )

        rich_result = SpellcheckResultV1(
            event_name=ProcessingEvent.SPELLCHECK_RESULTS,
            entity_id="test-essay-1",
            entity_type="essay",
            parent_id="batch-1",
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            system_metadata=SystemProcessingMetadata(
                entity_id="test-essay-1",
                entity_type="essay",
                parent_id="batch-1",
                timestamp=datetime.now(UTC),
            ),
            batch_id="batch-1",
            correlation_id=str(correlation_id),
            corrections_made=4,
            correction_metrics=metrics,
            original_text_storage_id="orig-123",
            corrected_text_storage_id="corrected-456",
            processing_duration_ms=1200,
        )

        result = await handler.handle_spellcheck_rich_result(rich_result, correlation_id)

        assert result is True
        mock_essay_repository.update_essay_processing_metadata.assert_called_once()
        metadata_updates = mock_essay_repository.update_essay_processing_metadata.call_args.kwargs[
            "metadata_updates"
        ]
        spellcheck_metadata = metadata_updates["spellcheck_result"]
        assert spellcheck_metadata["metrics"]["total_corrections"] == 4
        assert spellcheck_metadata["metrics"]["correction_density"] == 2.0
        assert spellcheck_metadata["corrections_made"] == 4

    @pytest.fixture
    def mock_cj_assessment_completed(self) -> MagicMock:
        """Create CJ assessment completed result data."""
        result = MagicMock()
        result.entity_id = "test-batch-1"
        result.entity_type = "batch"
        result.parent_id = None
        result.cj_assessment_job_id = "job-123"
        # New structure with processing_summary
        result.processing_summary = {
            "successful_essay_ids": ["essay-1", "essay-2"],
            "failed_essay_ids": [],
            "successful": 2,
            "failed": 0,
        }
        # Deprecated but kept for backward compatibility
        result.rankings = [
            {"els_essay_id": "essay-1", "rank": 1, "score": 0.85},
            {"els_essay_id": "essay-2", "rank": 2, "score": 0.75},
        ]
        return result

    @pytest.fixture
    def mock_cj_assessment_failed(self) -> MagicMock:
        """Create CJ assessment failed result data."""
        result = MagicMock()
        result.entity_id = "test-batch-1"
        result.entity_type = "batch"
        result.parent_id = None
        result.cj_assessment_job_id = "job-123"
        result.error_message = "CJ service unavailable"
        result.affected_essay_ids = ["essay-1", "essay-2"]
        return result

    async def test_handle_cj_assessment_completed_success(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_cj_assessment_completed: MagicMock,
    ) -> None:
        """Test successful CJ assessment completion handling."""
        # Setup
        correlation_id = uuid4()

        # Mock essay states - Set correct initial status for CJ assessment completion
        essay1_state = MagicMock()
        essay1_state.essay_id = "essay-1"
        essay1_state.current_status = EssayStatus.CJ_ASSESSMENT_IN_PROGRESS

        essay2_state = MagicMock()
        essay2_state.essay_id = "essay-2"
        essay2_state.current_status = EssayStatus.CJ_ASSESSMENT_IN_PROGRESS

        # The implementation calls get_essay_state for each ranking (2 essays)
        # then calls get_essay_state once more for the first essay to get batch representative state
        mock_essay_repository.get_essay_state.side_effect = [
            essay1_state,  # First essay get
            essay2_state,  # Second essay get
            essay1_state,  # Batch representative state get
        ]

        # Execute
        result = await handler.handle_cj_assessment_completed(
            mock_cj_assessment_completed, correlation_id
        )

        # Verify
        assert result is True
        assert (
            mock_essay_repository.get_essay_state.call_count == 3
        )  # 2 essays + 1 batch representative
        assert mock_essay_repository.update_essay_status_via_machine.call_count == 2
        assert mock_batch_coordinator.check_batch_completion.call_count == 1

    async def test_handle_cj_assessment_completed_essay_not_found(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_cj_assessment_completed: MagicMock,
    ) -> None:
        """Test CJ assessment completion when essay not found."""
        # Setup
        correlation_id = uuid4()
        mock_essay_repository.get_essay_state.return_value = None

        # Execute
        result = await handler.handle_cj_assessment_completed(
            mock_cj_assessment_completed, correlation_id
        )

        # Verify - should still return True but skip missing essays
        assert result is True
        mock_essay_repository.update_essay_status_via_machine.assert_not_called()
        mock_batch_coordinator.check_batch_completion.assert_not_called()

    async def test_handle_cj_assessment_failed_success(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_cj_assessment_failed: MagicMock,
    ) -> None:
        """Test CJ assessment failure handling."""
        # Setup
        correlation_id = uuid4()

        # Mock essay states - Set correct initial status for CJ assessment failure
        essay1_state = MagicMock()
        essay1_state.essay_id = "essay-1"
        essay1_state.current_status = EssayStatus.AWAITING_CJ_ASSESSMENT

        essay2_state = MagicMock()
        essay2_state.essay_id = "essay-2"
        essay2_state.current_status = EssayStatus.AWAITING_CJ_ASSESSMENT

        # Mock list_essays_by_batch call - implementation gets all essays then filters by status
        mock_essay_repository.list_essays_by_batch.return_value = [essay1_state, essay2_state]

        # Execute
        result = await handler.handle_cj_assessment_failed(
            mock_cj_assessment_failed, correlation_id
        )

        # Verify
        assert result is True
        mock_essay_repository.list_essays_by_batch.assert_called_once_with("test-batch-1")
        assert mock_essay_repository.update_essay_status_via_machine.call_count == 2

        # Check that failures were recorded properly
        for call in mock_essay_repository.update_essay_status_via_machine.call_args_list:
            assert call.args[1] == EssayStatus.CJ_ASSESSMENT_FAILED
            assert "cj_assessment_result" in call.args[2]
            assert call.args[2]["cj_assessment_result"]["success"] is False
            assert call.args[2]["cj_assessment_result"]["batch_failure"] is True

    async def test_handle_cj_assessment_failed_essay_not_found(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_cj_assessment_failed: MagicMock,
    ) -> None:
        """Test CJ assessment failure when essay not found."""
        # Setup
        correlation_id = uuid4()
        mock_essay_repository.get_essay_state.return_value = None

        # Execute
        result = await handler.handle_cj_assessment_failed(
            mock_cj_assessment_failed, correlation_id
        )

        # Verify - should still return True but skip missing essays
        assert result is True
        mock_essay_repository.update_essay_status_via_machine.assert_not_called()
