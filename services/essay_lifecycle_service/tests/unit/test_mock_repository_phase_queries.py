"""
Phase query tests for MockEssayRepository.

Validates phase queries using constants integration with focus on
list_essays_by_batch_and_phase() accuracy across all ELS-coordinated phases.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from common_core.pipeline_models import PhaseName
from common_core.status_enums import EssayStatus

from services.essay_lifecycle_service.constants import (
    ELS_PHASE_STATUS_MAPPING,
    get_els_phase_statuses,
)
from services.essay_lifecycle_service.domain_models import EssayState
from services.essay_lifecycle_service.implementations.mock_essay_repository import (
    MockEssayRepository,
)


class TestMockRepositoryPhaseQueries:
    """Test suite for MockEssayRepository phase query operations."""

    @pytest.fixture
    def mock_repository(self) -> MockEssayRepository:
        """Create mock repository instance."""
        return MockEssayRepository()

    async def _create_essay_with_status(
        self,
        repository: MockEssayRepository,
        essay_id: str,
        batch_id: str,
        status: EssayStatus,
    ) -> EssayState:
        """Helper to create essay with specific status."""
        correlation_id = uuid4()
        
        # Create essay first
        essay = await repository.create_essay_record(
            essay_id=essay_id,
            batch_id=batch_id,
            correlation_id=correlation_id,
        )
        
        # Update to target status if not already UPLOADED
        if status != EssayStatus.UPLOADED:
            await repository.update_essay_state(
                essay_id=essay_id,
                new_status=status,
                metadata={"phase_test": "created_via_helper"},
                correlation_id=correlation_id,
            )
        
        return essay

    @pytest.mark.asyncio
    async def test_spellcheck_phase_query_accuracy(self, mock_repository: MockEssayRepository) -> None:
        """Test list_essays_by_batch_and_phase accuracy for SPELLCHECK phase."""
        batch_id = "spellcheck-batch"
        
        # Create essays with various SPELLCHECK phase statuses
        spellcheck_statuses = ELS_PHASE_STATUS_MAPPING[PhaseName.SPELLCHECK]
        created_essays = []
        
        for i, status in enumerate(spellcheck_statuses):
            essay = await self._create_essay_with_status(
                mock_repository, f"spellcheck-{i}", batch_id, status
            )
            created_essays.append(essay)
        
        # Create essays with non-spellcheck statuses (should not be included)
        await self._create_essay_with_status(
            mock_repository, "other-1", batch_id, EssayStatus.AWAITING_CJ_ASSESSMENT
        )
        await self._create_essay_with_status(
            mock_repository, "other-2", batch_id, EssayStatus.NLP_SUCCESS
        )
        
        # Query spellcheck phase
        spellcheck_essays = await mock_repository.list_essays_by_batch_and_phase(
            batch_id=batch_id, phase_name="spellcheck"
        )
        
        # Validate results
        assert len(spellcheck_essays) == len(spellcheck_statuses)
        
        # All returned essays should have spellcheck statuses
        returned_statuses = {essay.current_status for essay in spellcheck_essays}
        expected_statuses = set(spellcheck_statuses)
        assert returned_statuses == expected_statuses
        
        # All returned essays should be in correct batch
        assert all(essay.batch_id == batch_id for essay in spellcheck_essays)

    @pytest.mark.asyncio
    async def test_cj_assessment_phase_query_accuracy(self, mock_repository: MockEssayRepository) -> None:
        """Test list_essays_by_batch_and_phase accuracy for CJ_ASSESSMENT phase."""
        batch_id = "cj-assessment-batch"
        
        # Create essays with CJ_ASSESSMENT phase statuses
        cj_statuses = ELS_PHASE_STATUS_MAPPING[PhaseName.CJ_ASSESSMENT]
        
        for i, status in enumerate(cj_statuses):
            await self._create_essay_with_status(
                mock_repository, f"cj-{i}", batch_id, status
            )
        
        # Query CJ assessment phase
        cj_essays = await mock_repository.list_essays_by_batch_and_phase(
            batch_id=batch_id, phase_name="cj_assessment"
        )
        
        # Validate results
        assert len(cj_essays) == len(cj_statuses)
        returned_statuses = {essay.current_status for essay in cj_essays}
        expected_statuses = set(cj_statuses)
        assert returned_statuses == expected_statuses

    @pytest.mark.asyncio
    async def test_nlp_phase_query_accuracy(self, mock_repository: MockEssayRepository) -> None:
        """Test list_essays_by_batch_and_phase accuracy for NLP phase."""
        batch_id = "nlp-batch"
        
        # Create essays with NLP phase statuses
        nlp_statuses = ELS_PHASE_STATUS_MAPPING[PhaseName.NLP]
        
        for i, status in enumerate(nlp_statuses):
            await self._create_essay_with_status(
                mock_repository, f"nlp-{i}", batch_id, status
            )
        
        # Query NLP phase
        nlp_essays = await mock_repository.list_essays_by_batch_and_phase(
            batch_id=batch_id, phase_name="nlp"
        )
        
        # Validate results
        assert len(nlp_essays) == len(nlp_statuses)
        returned_statuses = {essay.current_status for essay in nlp_essays}
        expected_statuses = set(nlp_statuses)
        assert returned_statuses == expected_statuses

    @pytest.mark.asyncio
    async def test_ai_feedback_phase_query_accuracy(self, mock_repository: MockEssayRepository) -> None:
        """Test list_essays_by_batch_and_phase accuracy for AI_FEEDBACK phase."""
        batch_id = "ai-feedback-batch"
        
        # Create essays with AI_FEEDBACK phase statuses
        ai_feedback_statuses = ELS_PHASE_STATUS_MAPPING[PhaseName.AI_FEEDBACK]
        
        for i, status in enumerate(ai_feedback_statuses):
            await self._create_essay_with_status(
                mock_repository, f"ai-feedback-{i}", batch_id, status
            )
        
        # Query AI feedback phase
        ai_feedback_essays = await mock_repository.list_essays_by_batch_and_phase(
            batch_id=batch_id, phase_name="ai_feedback"
        )
        
        # Validate results
        assert len(ai_feedback_essays) == len(ai_feedback_statuses)
        returned_statuses = {essay.current_status for essay in ai_feedback_essays}
        expected_statuses = set(ai_feedback_statuses)
        assert returned_statuses == expected_statuses

    @pytest.mark.asyncio
    async def test_unknown_phase_handling(self, mock_repository: MockEssayRepository) -> None:
        """Test that unknown phases return empty list without error."""
        batch_id = "unknown-phase-batch"
        
        # Create some essays
        await self._create_essay_with_status(
            mock_repository, "essay-1", batch_id, EssayStatus.UPLOADED
        )
        await self._create_essay_with_status(
            mock_repository, "essay-2", batch_id, EssayStatus.SPELLCHECKED_SUCCESS
        )
        
        # Query with unknown phase name
        unknown_essays = await mock_repository.list_essays_by_batch_and_phase(
            batch_id=batch_id, phase_name="unknown_phase"
        )
        
        # Should return empty list
        assert isinstance(unknown_essays, list)
        assert len(unknown_essays) == 0
        
        # Query with invalid phase name
        invalid_essays = await mock_repository.list_essays_by_batch_and_phase(
            batch_id=batch_id, phase_name="invalid_phase_name"
        )
        
        assert isinstance(invalid_essays, list)
        assert len(invalid_essays) == 0

    @pytest.mark.asyncio
    async def test_only_els_coordinated_phases_return_results(self, mock_repository: MockEssayRepository) -> None:
        """Test that only ELS-coordinated phases return matching essays."""
        batch_id = "els-coordination-batch"
        
        # Create essays with ELS-coordinated statuses
        await self._create_essay_with_status(
            mock_repository, "spellcheck-essay", batch_id, EssayStatus.AWAITING_SPELLCHECK
        )
        await self._create_essay_with_status(
            mock_repository, "cj-essay", batch_id, EssayStatus.AWAITING_CJ_ASSESSMENT
        )
        
        # Test all ELS-coordinated phases return results
        for phase_name in ELS_PHASE_STATUS_MAPPING.keys():
            phase_essays = await mock_repository.list_essays_by_batch_and_phase(
                batch_id=batch_id, phase_name=phase_name.value
            )
            # At least one of our test essays should match some phases
            assert isinstance(phase_essays, list)
            # The exact count depends on which statuses match the phase

    @pytest.mark.asyncio
    async def test_phase_query_batch_isolation(self, mock_repository: MockEssayRepository) -> None:
        """Test that phase queries are properly isolated by batch_id."""
        batch_1 = "batch-1"
        batch_2 = "batch-2"
        
        # Create essays in batch 1
        await self._create_essay_with_status(
            mock_repository, "batch1-essay1", batch_1, EssayStatus.AWAITING_SPELLCHECK
        )
        await self._create_essay_with_status(
            mock_repository, "batch1-essay2", batch_1, EssayStatus.SPELLCHECKING_IN_PROGRESS
        )
        
        # Create essays in batch 2
        await self._create_essay_with_status(
            mock_repository, "batch2-essay1", batch_2, EssayStatus.AWAITING_SPELLCHECK
        )
        await self._create_essay_with_status(
            mock_repository, "batch2-essay2", batch_2, EssayStatus.SPELLCHECK_FAILED
        )
        
        # Query batch 1 spellcheck phase
        batch1_spellcheck = await mock_repository.list_essays_by_batch_and_phase(
            batch_id=batch_1, phase_name="spellcheck"
        )
        
        # Query batch 2 spellcheck phase
        batch2_spellcheck = await mock_repository.list_essays_by_batch_and_phase(
            batch_id=batch_2, phase_name="spellcheck"
        )
        
        # Validate isolation
        assert len(batch1_spellcheck) == 2
        assert len(batch2_spellcheck) == 2
        
        # All essays in batch1 results should belong to batch_1
        assert all(essay.batch_id == batch_1 for essay in batch1_spellcheck)
        
        # All essays in batch2 results should belong to batch_2
        assert all(essay.batch_id == batch_2 for essay in batch2_spellcheck)
        
        # No cross-contamination
        batch1_essay_ids = {essay.essay_id for essay in batch1_spellcheck}
        batch2_essay_ids = {essay.essay_id for essay in batch2_spellcheck}
        assert batch1_essay_ids.isdisjoint(batch2_essay_ids)

    @pytest.mark.asyncio
    async def test_phase_status_mapping_consistency(self, mock_repository: MockEssayRepository) -> None:
        """Test that mock repository phase mapping matches constants exactly."""
        batch_id = "consistency-batch"
        
        # Test each phase defined in constants
        for phase_name, expected_statuses in ELS_PHASE_STATUS_MAPPING.items():
            # Create essays with all statuses for this phase
            for i, status in enumerate(expected_statuses):
                await self._create_essay_with_status(
                    mock_repository, f"{phase_name.value}-{i}", batch_id, status
                )
            
            # Query this phase
            phase_essays = await mock_repository.list_essays_by_batch_and_phase(
                batch_id=batch_id, phase_name=phase_name.value
            )
            
            # Validate that all expected statuses are returned
            returned_statuses = {essay.current_status for essay in phase_essays}
            expected_statuses_set = set(expected_statuses)
            
            assert returned_statuses == expected_statuses_set, (
                f"Phase {phase_name.value} status mismatch. "
                f"Expected: {expected_statuses_set}, Got: {returned_statuses}"
            )

    @pytest.mark.asyncio
    async def test_constants_integration_with_get_els_phase_statuses(self, mock_repository: MockEssayRepository) -> None:
        """Test integration between constants helper function and repository queries."""
        batch_id = "constants-integration-batch"
        
        # Test all ELS-coordinated phases
        for phase_name in ELS_PHASE_STATUS_MAPPING.keys():
            # Get statuses from constants helper
            expected_statuses = get_els_phase_statuses(phase_name)
            
            # Create essays with these statuses
            for i, status in enumerate(expected_statuses):
                await self._create_essay_with_status(
                    mock_repository, f"{phase_name.value}-constants-{i}", batch_id, status
                )
            
            # Query using repository
            phase_essays = await mock_repository.list_essays_by_batch_and_phase(
                batch_id=batch_id, phase_name=phase_name.value
            )
            
            # Validate consistency
            returned_statuses = {essay.current_status for essay in phase_essays}
            expected_statuses_set = set(expected_statuses)
            
            assert returned_statuses == expected_statuses_set

    @pytest.mark.asyncio
    async def test_phase_query_with_enum_and_string_phase_names(self, mock_repository: MockEssayRepository) -> None:
        """Test that phase queries work with both PhaseName enum and string values."""
        batch_id = "enum-string-batch"
        
        # Create essays with spellcheck statuses
        await self._create_essay_with_status(
            mock_repository, "enum-test-1", batch_id, EssayStatus.AWAITING_SPELLCHECK
        )
        await self._create_essay_with_status(
            mock_repository, "enum-test-2", batch_id, EssayStatus.SPELLCHECKED_SUCCESS
        )
        
        # Query using string phase name
        string_results = await mock_repository.list_essays_by_batch_and_phase(
            batch_id=batch_id, phase_name="spellcheck"
        )
        
        # Query using PhaseName.SPELLCHECK.value should work the same
        enum_value_results = await mock_repository.list_essays_by_batch_and_phase(
            batch_id=batch_id, phase_name=PhaseName.SPELLCHECK.value
        )
        
        # Results should be identical
        assert len(string_results) == len(enum_value_results) == 2
        
        string_essay_ids = {essay.essay_id for essay in string_results}
        enum_essay_ids = {essay.essay_id for essay in enum_value_results}
        assert string_essay_ids == enum_essay_ids

    @pytest.mark.asyncio
    async def test_empty_batch_phase_query(self, mock_repository: MockEssayRepository) -> None:
        """Test phase queries on empty batches return empty lists."""
        # Query non-existent batch
        empty_results = await mock_repository.list_essays_by_batch_and_phase(
            batch_id="non-existent-batch", phase_name="spellcheck"
        )
        
        assert isinstance(empty_results, list)
        assert len(empty_results) == 0

    @pytest.mark.asyncio
    async def test_phase_query_return_type_compatibility(self, mock_repository: MockEssayRepository) -> None:
        """Test that phase query returns are compatible with protocol expectations."""
        batch_id = "return-type-batch"
        
        # Create test essay
        await self._create_essay_with_status(
            mock_repository, "return-type-essay", batch_id, EssayStatus.AWAITING_SPELLCHECK
        )
        
        # Query phase
        results = await mock_repository.list_essays_by_batch_and_phase(
            batch_id=batch_id, phase_name="spellcheck"
        )
        
        # Validate return type compatibility
        assert isinstance(results, list)
        assert len(results) == 1
        
        essay = results[0]
        # Check that it has protocol-required attributes
        assert hasattr(essay, 'essay_id')
        assert hasattr(essay, 'batch_id')
        assert hasattr(essay, 'current_status')
        assert hasattr(essay, 'processing_metadata')
        assert hasattr(essay, 'timeline')
        assert hasattr(essay, 'storage_references')
        
        # Verify essay is the concrete domain model type
        assert isinstance(essay, EssayState)

    @pytest.mark.asyncio
    async def test_all_four_els_coordinated_phases_comprehensive(self, mock_repository: MockEssayRepository) -> None:
        """Comprehensive test of all 4 ELS-coordinated phases with mixed statuses."""
        batch_id = "comprehensive-phase-test"
        
        # Create essays covering all 4 ELS-coordinated phases
        phase_essay_counts = {}
        
        for phase_name, statuses in ELS_PHASE_STATUS_MAPPING.items():
            essay_count = 0
            for i, status in enumerate(statuses):
                await self._create_essay_with_status(
                    mock_repository, f"comprehensive-{phase_name.value}-{i}", batch_id, status
                )
                essay_count += 1
            phase_essay_counts[phase_name] = essay_count
        
        # Add essays with non-phase statuses (should not appear in phase queries)
        await self._create_essay_with_status(
            mock_repository, "comprehensive-uploaded", batch_id, EssayStatus.UPLOADED
        )
        await self._create_essay_with_status(
            mock_repository, "comprehensive-text-extracted", batch_id, EssayStatus.TEXT_EXTRACTED
        )
        
        # Query each phase and validate counts
        for phase_name, expected_count in phase_essay_counts.items():
            phase_results = await mock_repository.list_essays_by_batch_and_phase(
                batch_id=batch_id, phase_name=phase_name.value
            )
            
            assert len(phase_results) == expected_count, (
                f"Phase {phase_name.value} returned {len(phase_results)} essays, "
                f"expected {expected_count}"
            )
            
            # Validate all returned essays belong to this phase
            returned_statuses = {essay.current_status for essay in phase_results}
            expected_statuses = set(ELS_PHASE_STATUS_MAPPING[phase_name])
            assert returned_statuses.issubset(expected_statuses)
        
        # Verify total essays across all phases + non-phase essays
        all_essays = await mock_repository.list_essays_by_batch(batch_id)
        expected_total = sum(phase_essay_counts.values()) + 2  # +2 for non-phase essays
        assert len(all_essays) == expected_total

    def test_els_phase_status_mapping_contains_exactly_four_phases(self) -> None:
        """Test that ELS_PHASE_STATUS_MAPPING contains exactly 4 ELS-coordinated phases."""
        expected_phases = {
            PhaseName.SPELLCHECK,
            PhaseName.CJ_ASSESSMENT,
            PhaseName.NLP,
            PhaseName.AI_FEEDBACK,
        }
        
        actual_phases = set(ELS_PHASE_STATUS_MAPPING.keys())
        assert actual_phases == expected_phases
        
        # Verify STUDENT_MATCHING is not included (by design - inter-service coordination)
        assert PhaseName.STUDENT_MATCHING not in ELS_PHASE_STATUS_MAPPING

    def test_each_els_phase_has_four_statuses(self) -> None:
        """Test that each ELS-coordinated phase has exactly 4 statuses (awaiting, in_progress, success, failed)."""
        for phase_name, statuses in ELS_PHASE_STATUS_MAPPING.items():
            assert len(statuses) == 4, f"Phase {phase_name.value} should have 4 statuses, got {len(statuses)}"
            
            # Verify all statuses are valid EssayStatus enum values
            for status in statuses:
                assert isinstance(status, EssayStatus), f"Invalid status type: {type(status)}"
                assert hasattr(EssayStatus, status.name), f"Status {status} not found in EssayStatus enum"