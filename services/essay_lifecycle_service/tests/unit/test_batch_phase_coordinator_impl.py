"""
Unit tests for DefaultBatchPhaseCoordinator implementation.

Tests the batch phase coordinator's aggregation logic and
ELSBatchPhaseOutcomeV1 event publishing for Task 2.3.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, ANY
from uuid import uuid4

import pytest
from common_core.domain_enums import ContentType
from common_core.pipeline_models import PhaseName
from common_core.status_enums import BatchStatus, EssayStatus

from services.essay_lifecycle_service.implementations.batch_phase_coordinator_impl import (
    DefaultBatchPhaseCoordinator,
)
from services.essay_lifecycle_service.protocols import (
    BatchEssayTracker,
    EssayRepositoryProtocol,
    EventPublisher,
)
from services.essay_lifecycle_service.tests.unit.test_utils import mock_session_factory


class TestDefaultBatchPhaseCoordinator:
    """Test suite for DefaultBatchPhaseCoordinator."""

    @pytest.fixture
    def mock_essay_repository(self) -> AsyncMock:
        """Mock EssayRepositoryProtocol for testing using protocol-based mocking."""
        return AsyncMock(spec=EssayRepositoryProtocol)

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Mock EventPublisher for testing using protocol-based mocking."""
        return AsyncMock(spec=EventPublisher)

    @pytest.fixture
    def mock_batch_tracker(self) -> AsyncMock:
        """Mock BatchEssayTracker for testing using protocol-based mocking."""
        return AsyncMock(spec=BatchEssayTracker)

    # Using shared mock_session_factory fixture from test_utils

    @pytest.fixture
    def coordinator(
        self,
        mock_essay_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_batch_tracker: AsyncMock,
        mock_session_factory: AsyncMock,
    ) -> DefaultBatchPhaseCoordinator:
        """Create DefaultBatchPhaseCoordinator instance for testing."""
        return DefaultBatchPhaseCoordinator(
            repository=mock_essay_repository,
            event_publisher=mock_event_publisher,
            batch_tracker=mock_batch_tracker,
            session_factory=mock_session_factory,
        )

    def create_mock_essay_state(
        self,
        essay_id: str,
        batch_id: str,
        status: EssayStatus,
        phase: str,
        storage_refs: dict[ContentType, str] | None = None,
    ) -> MagicMock:
        """Helper to create mock essay states with different configurations."""
        essay_state = MagicMock()
        essay_state.essay_id = essay_id
        essay_state.batch_id = batch_id
        essay_state.current_status = status
        essay_state.processing_metadata = {"current_phase": phase, "commanded_phases": [phase]}

        # Set storage_references as a real dictionary to avoid MagicMock interference
        final_storage_refs = storage_refs or {ContentType.ORIGINAL_ESSAY: f"original-{essay_id}"}
        essay_state.storage_references = final_storage_refs

        # Ensure MagicMock doesn't auto-create storage-related attributes
        essay_state.spellchecked_text_storage_id = None
        essay_state.ai_feedback_text_storage_id = None
        essay_state.cj_assessment_text_storage_id = None
        essay_state.nlp_processed_text_storage_id = None

        return essay_state

    async def test_check_batch_completion_all_succeed_triggers_outcome(
        self,
        coordinator: DefaultBatchPhaseCoordinator,
        mock_essay_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test batch completion when all essays succeed triggers outcome event."""
        # Setup
        correlation_id = uuid4()

        # Create test essay state to trigger the check
        test_essay_state = self.create_mock_essay_state(
            "trigger-essay", "test-batch-1", EssayStatus.SPELLCHECKED_SUCCESS, "spellcheck"
        )

        # Create multiple successful essays
        essay1 = self.create_mock_essay_state(
            "essay-1",
            "test-batch-1",
            EssayStatus.SPELLCHECKED_SUCCESS,
            "spellcheck",
            {ContentType.ORIGINAL_ESSAY: "original-1", ContentType.CORRECTED_TEXT: "corrected-1"},
        )
        essay2 = self.create_mock_essay_state(
            "essay-2",
            "test-batch-1",
            EssayStatus.SPELLCHECKED_SUCCESS,
            "spellcheck",
            {ContentType.ORIGINAL_ESSAY: "original-2", ContentType.CORRECTED_TEXT: "corrected-2"},
        )

        mock_essay_repository.list_essays_by_batch_and_phase.return_value = [essay1, essay2]

        # Execute
        await coordinator.check_batch_completion(
            test_essay_state, PhaseName.SPELLCHECK, correlation_id, ANY  # session
        )

        # Verify
        mock_essay_repository.list_essays_by_batch_and_phase.assert_called_once_with(
            batch_id="test-batch-1", phase_name="spellcheck"
        )

        mock_event_publisher.publish_els_batch_phase_outcome.assert_called_once()

        # Check the event data
        call_args = mock_event_publisher.publish_els_batch_phase_outcome.call_args
        event_data = call_args.kwargs["event_data"]  # Keyword argument

        assert event_data.batch_id == "test-batch-1"
        assert event_data.phase_name == PhaseName.SPELLCHECK
        assert event_data.phase_status == BatchStatus.COMPLETED_SUCCESSFULLY
        assert len(event_data.processed_essays) == 2
        assert len(event_data.failed_essay_ids) == 0

        # Verify processed essays have correct storage IDs
        processed_essay_ids = [essay.essay_id for essay in event_data.processed_essays]
        assert "essay-1" in processed_essay_ids
        assert "essay-2" in processed_essay_ids

    async def test_check_batch_completion_some_fail_triggers_outcome(
        self,
        coordinator: DefaultBatchPhaseCoordinator,
        mock_essay_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test batch completion with mixed success/failure triggers outcome event."""
        # Setup
        correlation_id = uuid4()

        # Create test essay state to trigger the check
        test_essay_state = self.create_mock_essay_state(
            "trigger-essay", "test-batch-1", EssayStatus.SPELLCHECKED_SUCCESS, "spellcheck"
        )

        # Create mixed success/failure essays
        essay1_success = self.create_mock_essay_state(
            "essay-1",
            "test-batch-1",
            EssayStatus.SPELLCHECKED_SUCCESS,
            "spellcheck",
            {ContentType.CORRECTED_TEXT: "corrected-1"},
        )
        essay2_failed = self.create_mock_essay_state(
            "essay-2", "test-batch-1", EssayStatus.SPELLCHECK_FAILED, "spellcheck"
        )
        essay3_success = self.create_mock_essay_state(
            "essay-3",
            "test-batch-1",
            EssayStatus.SPELLCHECKED_SUCCESS,
            "spellcheck",
            {ContentType.CORRECTED_TEXT: "corrected-3"},
        )

        mock_essay_repository.list_essays_by_batch_and_phase.return_value = [
            essay1_success,
            essay2_failed,
            essay3_success,
        ]

        # Execute
        await coordinator.check_batch_completion(
            test_essay_state, PhaseName.SPELLCHECK, correlation_id, ANY  # session
        )

        # Verify
        mock_event_publisher.publish_els_batch_phase_outcome.assert_called_once()

        # Check the event data
        call_args = mock_event_publisher.publish_els_batch_phase_outcome.call_args
        event_data = call_args.kwargs["event_data"]

        assert event_data.batch_id == "test-batch-1"
        assert event_data.phase_name == PhaseName.SPELLCHECK
        assert event_data.phase_status == BatchStatus.COMPLETED_WITH_FAILURES
        assert len(event_data.processed_essays) == 2  # Only successful ones
        assert len(event_data.failed_essay_ids) == 1
        assert "essay-2" in event_data.failed_essay_ids

    async def test_check_batch_completion_all_fail_triggers_outcome(
        self,
        coordinator: DefaultBatchPhaseCoordinator,
        mock_essay_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test batch completion when all essays fail triggers outcome event."""
        # Setup
        correlation_id = uuid4()

        # Create test essay state to trigger the check
        test_essay_state = self.create_mock_essay_state(
            "trigger-essay", "test-batch-1", EssayStatus.SPELLCHECK_FAILED, "spellcheck"
        )

        # Create all failed essays
        essay1_failed = self.create_mock_essay_state(
            "essay-1", "test-batch-1", EssayStatus.SPELLCHECK_FAILED, "spellcheck"
        )
        essay2_failed = self.create_mock_essay_state(
            "essay-2", "test-batch-1", EssayStatus.SPELLCHECK_FAILED, "spellcheck"
        )

        mock_essay_repository.list_essays_by_batch_and_phase.return_value = [
            essay1_failed,
            essay2_failed,
        ]

        # Execute
        await coordinator.check_batch_completion(
            test_essay_state, PhaseName.SPELLCHECK, correlation_id, ANY  # session
        )

        # Verify
        mock_event_publisher.publish_els_batch_phase_outcome.assert_called_once()

        # Check the event data
        call_args = mock_event_publisher.publish_els_batch_phase_outcome.call_args
        event_data = call_args.kwargs["event_data"]

        assert event_data.batch_id == "test-batch-1"
        assert event_data.phase_name == PhaseName.SPELLCHECK
        assert event_data.phase_status == BatchStatus.FAILED_CRITICALLY
        assert len(event_data.processed_essays) == 0
        assert len(event_data.failed_essay_ids) == 2
        assert "essay-1" in event_data.failed_essay_ids
        assert "essay-2" in event_data.failed_essay_ids

    async def test_check_batch_completion_not_all_done_no_outcome(
        self,
        coordinator: DefaultBatchPhaseCoordinator,
        mock_essay_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test batch completion when essays still processing - no outcome event."""
        # Setup
        correlation_id = uuid4()

        # Create test essay state to trigger the check
        test_essay_state = self.create_mock_essay_state(
            "trigger-essay", "test-batch-1", EssayStatus.SPELLCHECKING_IN_PROGRESS, "spellcheck"
        )

        # Create essays with some still processing
        essay1_success = self.create_mock_essay_state(
            "essay-1", "test-batch-1", EssayStatus.SPELLCHECKED_SUCCESS, "spellcheck"
        )
        essay2_processing = self.create_mock_essay_state(
            "essay-2", "test-batch-1", EssayStatus.SPELLCHECKING_IN_PROGRESS, "spellcheck"
        )
        essay3_waiting = self.create_mock_essay_state(
            "essay-3", "test-batch-1", EssayStatus.AWAITING_SPELLCHECK, "spellcheck"
        )

        mock_essay_repository.list_essays_by_batch_and_phase.return_value = [
            essay1_success,
            essay2_processing,
            essay3_waiting,
        ]

        # Execute
        await coordinator.check_batch_completion(
            test_essay_state, PhaseName.SPELLCHECK, correlation_id, ANY  # session
        )

        # Verify - no outcome event should be published
        mock_event_publisher.publish_els_batch_phase_outcome.assert_not_called()

    async def test_check_batch_completion_essay_not_in_phase_no_outcome(
        self,
        coordinator: DefaultBatchPhaseCoordinator,
        mock_essay_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test batch completion when essay not part of the specified phase - no outcome event."""
        # Setup
        correlation_id = uuid4()

        # Essay not part of this phase
        essay_state_wrong_phase = MagicMock()
        essay_state_wrong_phase.essay_id = "test-essay-1"
        essay_state_wrong_phase.batch_id = "test-batch-1"
        essay_state_wrong_phase.processing_metadata = {
            "current_phase": "cj_assessment",  # Different phase
            "commanded_phases": ["cj_assessment"],
        }

        # Execute
        await coordinator.check_batch_completion(
            essay_state_wrong_phase, "spellcheck", correlation_id, ANY  # session
        )

        # Verify - no database call or event publishing should occur
        mock_essay_repository.list_essays_by_batch_and_phase.assert_not_called()
        mock_event_publisher.publish_els_batch_phase_outcome.assert_not_called()

    async def test_check_batch_completion_no_batch_id_no_outcome(
        self,
        coordinator: DefaultBatchPhaseCoordinator,
        mock_essay_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test batch completion when essay has no batch ID - no outcome event."""
        # Setup
        correlation_id = uuid4()

        # Essay without batch ID
        essay_state_no_batch = MagicMock()
        essay_state_no_batch.essay_id = "test-essay-1"
        essay_state_no_batch.batch_id = None

        # Execute
        await coordinator.check_batch_completion(essay_state_no_batch, "spellcheck", correlation_id, ANY)  # session

        # Verify - no database call or event publishing should occur
        mock_essay_repository.list_essays_by_batch_and_phase.assert_not_called()
        mock_event_publisher.publish_els_batch_phase_outcome.assert_not_called()

    async def test_get_text_storage_id_for_phase_logic(
        self, coordinator: DefaultBatchPhaseCoordinator
    ) -> None:
        """Test _get_text_storage_id_for_phase logic for different phases."""
        # Test spellcheck phase - should return CORRECTED_TEXT
        essay_spellcheck = self.create_mock_essay_state(
            "essay-1",
            "batch-1",
            EssayStatus.SPELLCHECKED_SUCCESS,
            "spellcheck",
            {ContentType.ORIGINAL_ESSAY: "original-1", ContentType.CORRECTED_TEXT: "corrected-1"},
        )

        storage_id = coordinator._get_text_storage_id_for_phase(essay_spellcheck, "spellcheck")
        assert storage_id == "corrected-1"

        # Test CJ assessment phase - should return ORIGINAL_ESSAY (fallback)
        essay_cj = self.create_mock_essay_state(
            "essay-2",
            "batch-1",
            EssayStatus.CJ_ASSESSMENT_SUCCESS,
            "cj_assessment",
            {ContentType.ORIGINAL_ESSAY: "original-2"},
        )

        storage_id = coordinator._get_text_storage_id_for_phase(essay_cj, "cj_assessment")
        assert storage_id == "original-2"

        # Test missing storage reference - should fall back to original
        essay_no_storage = self.create_mock_essay_state(
            "essay-3",
            "batch-1",
            EssayStatus.SPELLCHECKED_SUCCESS,
            "spellcheck",
            {},  # No storage references
        )

        storage_id = coordinator._get_text_storage_id_for_phase(essay_no_storage, "spellcheck")
        assert storage_id == "original-essay-3"  # Falls back to original

    def test_get_terminal_statuses_for_phase(
        self, coordinator: DefaultBatchPhaseCoordinator
    ) -> None:
        """Test _get_terminal_statuses_for_phase method."""
        # Test spellcheck phase
        spellcheck_terminals = coordinator._get_terminal_statuses_for_phase("spellcheck")
        expected_spellcheck = {EssayStatus.SPELLCHECKED_SUCCESS, EssayStatus.SPELLCHECK_FAILED}
        assert spellcheck_terminals == expected_spellcheck

        # Test CJ assessment phase
        cj_terminals = coordinator._get_terminal_statuses_for_phase("cj_assessment")
        expected_cj = {EssayStatus.CJ_ASSESSMENT_SUCCESS, EssayStatus.CJ_ASSESSMENT_FAILED}
        assert cj_terminals == expected_cj

        # Test unknown phase
        unknown_terminals = coordinator._get_terminal_statuses_for_phase("unknown_phase")
        assert unknown_terminals == set()

    def test_is_success_status_for_phase(self, coordinator: DefaultBatchPhaseCoordinator) -> None:
        """Test _is_success_status_for_phase method."""
        # Test spellcheck success
        assert (
            coordinator._is_success_status_for_phase(EssayStatus.SPELLCHECKED_SUCCESS, "spellcheck")
            is True
        )
        assert (
            coordinator._is_success_status_for_phase(EssayStatus.SPELLCHECK_FAILED, "spellcheck")
            is False
        )

        # Test CJ assessment success
        assert (
            coordinator._is_success_status_for_phase(
                EssayStatus.CJ_ASSESSMENT_SUCCESS, "cj_assessment"
            )
            is True
        )
        assert (
            coordinator._is_success_status_for_phase(
                EssayStatus.CJ_ASSESSMENT_FAILED, "cj_assessment"
            )
            is False
        )

        # Test wrong phase
        assert (
            coordinator._is_success_status_for_phase(
                EssayStatus.SPELLCHECKED_SUCCESS, "cj_assessment"
            )
            is False
        )

    async def test_check_batch_completion_cj_assessment_phase(
        self,
        coordinator: DefaultBatchPhaseCoordinator,
        mock_essay_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test batch completion for CJ assessment phase specifically."""
        # Setup
        correlation_id = uuid4()

        # Create CJ assessment essay state
        essay_state_cj = self.create_mock_essay_state(
            "essay-1", "test-batch-1", EssayStatus.CJ_ASSESSMENT_SUCCESS, "cj_assessment"
        )

        # Create completed CJ assessment essays
        essay1_success = self.create_mock_essay_state(
            "essay-1", "test-batch-1", EssayStatus.CJ_ASSESSMENT_SUCCESS, "cj_assessment"
        )
        essay2_success = self.create_mock_essay_state(
            "essay-2", "test-batch-1", EssayStatus.CJ_ASSESSMENT_SUCCESS, "cj_assessment"
        )

        mock_essay_repository.list_essays_by_batch_and_phase.return_value = [
            essay1_success,
            essay2_success,
        ]

        # Execute
        await coordinator.check_batch_completion(essay_state_cj, "cj_assessment", correlation_id, ANY)  # session

        # Verify
        mock_event_publisher.publish_els_batch_phase_outcome.assert_called_once()

        # Check the event data
        call_args = mock_event_publisher.publish_els_batch_phase_outcome.call_args
        event_data = call_args.kwargs["event_data"]

        assert event_data.batch_id == "test-batch-1"
        assert event_data.phase_name == "cj_assessment"
        assert event_data.phase_status == BatchStatus.COMPLETED_SUCCESSFULLY
        assert len(event_data.processed_essays) == 2
        assert len(event_data.failed_essay_ids) == 0
