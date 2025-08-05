"""
Tests for Essay Lifecycle Service constants and helper functions.

Validates constants.py helper functions, integration with the mock repository,
and error handling for ELS-specific constants and mappings.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from common_core.pipeline_models import PhaseName
from common_core.status_enums import EssayStatus

from services.essay_lifecycle_service.constants import (
    ELS_PHASE_STATUS_MAPPING,
    BatchCoordination,
    EssayDefaults,
    MetadataKey,
    QueryLimits,
    RepositoryOperation,
    ServiceResultStatus,
    get_els_phase_statuses,
)
from services.essay_lifecycle_service.implementations.mock_essay_repository import (
    MockEssayRepository,
)
from services.essay_lifecycle_service.tests.unit.test_data_builders import (
    EssayTestDataBuilder,
)


class TestGetElsPhaseStatusesFunction:
    """Test suite for get_els_phase_statuses() helper function."""

    @pytest.mark.parametrize(
        "phase_name",
        [
            PhaseName.SPELLCHECK,
            PhaseName.CJ_ASSESSMENT,
            PhaseName.NLP,
            PhaseName.AI_FEEDBACK,
        ],
    )
    def test_get_els_phase_statuses_returns_correct_statuses_for_valid_phases(
        self, phase_name: PhaseName
    ) -> None:
        """Test that get_els_phase_statuses returns correct statuses for ELS-coordinated phases."""
        statuses = get_els_phase_statuses(phase_name)

        # Verify return type
        assert isinstance(statuses, list)
        assert len(statuses) == 4, (
            f"Expected 4 statuses for {phase_name.value}, got {len(statuses)}"
        )
        assert all(isinstance(status, EssayStatus) for status in statuses)

        # Verify statuses match the mapping
        expected_statuses = ELS_PHASE_STATUS_MAPPING[phase_name]
        assert statuses == expected_statuses

        # Verify statuses follow actual ELS patterns based on real data
        status_values = [status.value for status in statuses]
        assert any("awaiting_" in status for status in status_values), (
            f"No awaiting status found in {status_values}"
        )
        # Progress pattern varies: "spellchecking_in_progress" vs "*_processing_in_progress"
        assert any("progress" in status for status in status_values), (
            f"No progress status found in {status_values}"
        )
        assert any("_success" in status for status in status_values), (
            f"No success status found in {status_values}"
        )
        assert any("_failed" in status for status in status_values), (
            f"No failed status found in {status_values}"
        )

    @pytest.mark.parametrize(
        "phase_name_str",
        ["spellcheck", "cj_assessment", "nlp", "ai_feedback"],
    )
    def test_get_els_phase_statuses_accepts_string_phase_names(self, phase_name_str: str) -> None:
        """Test that get_els_phase_statuses accepts string phase names."""
        statuses = get_els_phase_statuses(phase_name_str)

        # Verify it works with string input
        assert isinstance(statuses, list)
        assert len(statuses) == 4
        assert all(isinstance(status, EssayStatus) for status in statuses)

        # Compare with enum version
        phase_enum = PhaseName(phase_name_str)
        enum_statuses = get_els_phase_statuses(phase_enum)
        assert statuses == enum_statuses

    def test_get_els_phase_statuses_spellcheck_specific(self) -> None:
        """Test get_els_phase_statuses returns correct spellcheck statuses."""
        statuses = get_els_phase_statuses(PhaseName.SPELLCHECK)

        expected_statuses = [
            EssayStatus.AWAITING_SPELLCHECK,
            EssayStatus.SPELLCHECKING_IN_PROGRESS,
            EssayStatus.SPELLCHECKED_SUCCESS,
            EssayStatus.SPELLCHECK_FAILED,
        ]

        assert statuses == expected_statuses

    def test_get_els_phase_statuses_cj_assessment_specific(self) -> None:
        """Test get_els_phase_statuses returns correct CJ assessment statuses."""
        statuses = get_els_phase_statuses(PhaseName.CJ_ASSESSMENT)

        expected_statuses = [
            EssayStatus.AWAITING_CJ_ASSESSMENT,
            EssayStatus.CJ_ASSESSMENT_IN_PROGRESS,
            EssayStatus.CJ_ASSESSMENT_SUCCESS,
            EssayStatus.CJ_ASSESSMENT_FAILED,
        ]

        assert statuses == expected_statuses

    def test_get_els_phase_statuses_nlp_specific(self) -> None:
        """Test get_els_phase_statuses returns correct NLP statuses."""
        statuses = get_els_phase_statuses(PhaseName.NLP)

        expected_statuses = [
            EssayStatus.AWAITING_NLP,
            EssayStatus.NLP_IN_PROGRESS,
            EssayStatus.NLP_SUCCESS,
            EssayStatus.NLP_FAILED,
        ]

        assert statuses == expected_statuses

    def test_get_els_phase_statuses_ai_feedback_specific(self) -> None:
        """Test get_els_phase_statuses returns correct AI feedback statuses."""
        statuses = get_els_phase_statuses(PhaseName.AI_FEEDBACK)

        expected_statuses = [
            EssayStatus.AWAITING_AI_FEEDBACK,
            EssayStatus.AI_FEEDBACK_IN_PROGRESS,
            EssayStatus.AI_FEEDBACK_SUCCESS,
            EssayStatus.AI_FEEDBACK_FAILED,
        ]

        assert statuses == expected_statuses

    def test_get_els_phase_statuses_raises_for_unknown_string_phase(self) -> None:
        """Test that get_els_phase_statuses raises ValueError for unknown string phases."""
        with pytest.raises(ValueError) as exc_info:
            get_els_phase_statuses("unknown_phase")

        error_message = str(exc_info.value)
        assert "Unknown phase 'unknown_phase'" in error_message
        assert "ELS-coordinated phases" in error_message

    def test_get_els_phase_statuses_raises_for_student_matching_phase(self) -> None:
        """Test that get_els_phase_statuses raises ValueError for STUDENT_MATCHING phase."""
        # STUDENT_MATCHING is not ELS-coordinated by design
        with pytest.raises(ValueError) as exc_info:
            get_els_phase_statuses(PhaseName.STUDENT_MATCHING)

        error_message = str(exc_info.value)
        assert "student_matching" in error_message  # Actual error uses lowercase phase value
        assert "is not ELS-coordinated" in error_message
        assert "ELS-coordinated phases" in error_message


class TestElsPhaseStatusMapping:
    """Test suite for ELS_PHASE_STATUS_MAPPING constant validation."""

    def test_els_phase_status_mapping_completeness(self) -> None:
        """Test that ELS_PHASE_STATUS_MAPPING contains exactly 4 ELS-coordinated phases."""
        expected_phases = {
            PhaseName.SPELLCHECK,
            PhaseName.CJ_ASSESSMENT,
            PhaseName.NLP,
            PhaseName.AI_FEEDBACK,
        }

        actual_phases = set(ELS_PHASE_STATUS_MAPPING.keys())
        assert actual_phases == expected_phases

        # Verify STUDENT_MATCHING is NOT included (inter-service coordination)
        assert PhaseName.STUDENT_MATCHING not in ELS_PHASE_STATUS_MAPPING

    def test_els_phase_status_mapping_status_counts(self) -> None:
        """Test that each ELS phase has exactly 4 statuses."""
        for phase_name, statuses in ELS_PHASE_STATUS_MAPPING.items():
            assert len(statuses) == 4, (
                f"Phase {phase_name.value} should have 4 statuses, got {len(statuses)}"
            )
            assert all(isinstance(status, EssayStatus) for status in statuses)

    def test_els_phase_status_mapping_status_validity(self) -> None:
        """Test that all statuses in ELS_PHASE_STATUS_MAPPING are valid EssayStatus values."""
        all_statuses = []
        for statuses in ELS_PHASE_STATUS_MAPPING.values():
            all_statuses.extend(statuses)

        # Verify no duplicates across phases
        assert len(all_statuses) == len(set(all_statuses)), "Duplicate statuses found across phases"

        # Verify all are valid EssayStatus enum values
        valid_essay_statuses = set(EssayStatus)
        for status in all_statuses:
            assert status in valid_essay_statuses, f"Invalid EssayStatus: {status}"

    def test_els_phase_status_mapping_status_patterns(self) -> None:
        """Test that each phase follows expected status patterns."""
        for phase_name, statuses in ELS_PHASE_STATUS_MAPPING.items():
            status_values = [status.value for status in statuses]
            phase_value = phase_name.value  # Use actual phase value (lowercase)

            # Each phase should have its own phase-specific statuses
            # Look for the phase name in the status values (both are lowercase)
            phase_statuses = [s for s in status_values if phase_value in s]
            assert len(phase_statuses) >= 3, (
                f"Phase {phase_name.value} should have at least 3 phase-specific statuses, found: {phase_statuses}"
            )

    def test_els_phase_status_mapping_immutability(self) -> None:
        """Test that ELS_PHASE_STATUS_MAPPING structure remains consistent."""
        # Document the expected structure for regression testing
        expected_structure = {
            PhaseName.SPELLCHECK: 4,
            PhaseName.CJ_ASSESSMENT: 4,
            PhaseName.NLP: 4,
            PhaseName.AI_FEEDBACK: 4,
        }

        for phase, expected_count in expected_structure.items():
            assert phase in ELS_PHASE_STATUS_MAPPING
            assert len(ELS_PHASE_STATUS_MAPPING[phase]) == expected_count

    def test_missing_student_matching_verification(self) -> None:
        """Test that STUDENT_MATCHING is deliberately missing from ELS coordination."""
        # This is by design - STUDENT_MATCHING is handled via inter-service coordination
        # and does not have ELS-internal status transitions

        assert PhaseName.STUDENT_MATCHING not in ELS_PHASE_STATUS_MAPPING

        # Verify this raises an appropriate error
        with pytest.raises(ValueError):
            get_els_phase_statuses(PhaseName.STUDENT_MATCHING)


class TestConstantsIntegration:
    """Test suite for constants integration with repository operations."""

    @pytest.fixture
    def mock_repository(self) -> MockEssayRepository:
        """Create mock repository instance."""
        return MockEssayRepository()

    @pytest.mark.asyncio
    async def test_constants_usage_in_repository_phase_queries(
        self, mock_repository: MockEssayRepository
    ) -> None:
        """Test that constants are used correctly in repository phase queries."""
        batch_id = "constants-integration-batch"

        # Create test data using constants
        await EssayTestDataBuilder.create_batch_with_phase_distribution(
            repository=mock_repository,
            batch_id=batch_id,
            phase_distributions={"spellcheck": 3, "cj_assessment": 2},
        )

        # Test phase queries using constants
        spellcheck_essays = await mock_repository.list_essays_by_batch_and_phase(
            batch_id=batch_id,
            phase_name="spellcheck",
        )

        # Verify results match constants expectations
        assert len(spellcheck_essays) == 3

        # Verify all returned essays have statuses from ELS_PHASE_STATUS_MAPPING
        spellcheck_statuses = ELS_PHASE_STATUS_MAPPING[PhaseName.SPELLCHECK]
        for essay in spellcheck_essays:
            assert essay.current_status in spellcheck_statuses

    @pytest.mark.asyncio
    async def test_metadata_key_constants_usage(self, mock_repository: MockEssayRepository) -> None:
        """Test that MetadataKey constants are used correctly in repository operations."""
        correlation_id = uuid4()
        essay_id = "metadata-constants-test"
        batch_id = "metadata-batch"

        # Create essay
        await mock_repository.create_essay_record(
            essay_id=essay_id,
            batch_id=batch_id,
            correlation_id=correlation_id,
        )

        # Update using MetadataKey constants
        metadata_updates = {
            MetadataKey.CURRENT_PHASE: "spellcheck",
            MetadataKey.COMMANDED_PHASES: ["spellcheck", "cj_assessment"],
            MetadataKey.PHASE_INITIATED_AT: "2024-01-01T00:00:00Z",
            MetadataKey.PROCESSING_ATTEMPT_COUNT: 1,
        }

        await mock_repository.update_essay_processing_metadata(
            essay_id=essay_id,
            metadata_updates=metadata_updates,
            correlation_id=correlation_id,
        )

        # Verify constants were used correctly
        updated_essay = await mock_repository.get_essay_state(essay_id)
        assert updated_essay is not None

        # Check all metadata constants are present and correct
        for key, expected_value in metadata_updates.items():
            assert key in updated_essay.processing_metadata
            assert updated_essay.processing_metadata[key] == expected_value

    @pytest.mark.asyncio
    async def test_essay_defaults_constants_usage(
        self, mock_repository: MockEssayRepository
    ) -> None:
        """Test that EssayDefaults constants are applied correctly."""
        correlation_id = uuid4()
        essay_id = "defaults-test"

        # Create essay and verify defaults
        created_essay = await mock_repository.create_essay_record(
            essay_id=essay_id,
            batch_id="defaults-batch",
            entity_type=EssayDefaults.ENTITY_TYPE,
            correlation_id=correlation_id,
        )

        # Verify default metadata is applied
        assert (
            created_essay.processing_metadata[MetadataKey.ENTITY_TYPE] == EssayDefaults.ENTITY_TYPE
        )

    def test_repository_operation_constants_coverage(self) -> None:
        """Test that RepositoryOperation constants cover all major operations."""
        # Verify that RepositoryOperation constants exist for key operations
        expected_operations = [
            RepositoryOperation.CREATE_ESSAY_RECORD,
            RepositoryOperation.UPDATE_ESSAY_STATE,
            RepositoryOperation.GET_ESSAY_STATE,
            RepositoryOperation.CREATE_ESSAY_RECORDS_BATCH,
            RepositoryOperation.LIST_ESSAYS_BY_BATCH,
            RepositoryOperation.LIST_ESSAYS_BY_BATCH_AND_PHASE,
            RepositoryOperation.GET_BATCH_STATUS_SUMMARY,
            RepositoryOperation.CREATE_WITH_CONTENT_IDEMPOTENCY,
        ]

        # Verify all operation constants are defined and are strings
        for operation in expected_operations:
            assert isinstance(operation, str)
            assert len(operation) > 0
            # Operation names should be snake_case
            assert operation.islower() or "_" in operation


class TestServiceResultConstants:
    """Test suite for service result handling constants."""

    def test_service_result_status_constants(self) -> None:
        """Test that ServiceResultStatus constants are properly defined."""
        expected_statuses = [
            ServiceResultStatus.SUCCESS,
            ServiceResultStatus.FAILED,
            ServiceResultStatus.RETRY_NEEDED,
            ServiceResultStatus.PERMANENTLY_FAILED,
        ]

        for status in expected_statuses:
            assert isinstance(status, str)
            assert len(status) > 0

        # Verify unique values
        assert len(set(expected_statuses)) == len(expected_statuses)

    def test_batch_coordination_constants(self) -> None:
        """Test that BatchCoordination constants are reasonable."""
        # Test completion thresholds
        assert 0 < BatchCoordination.MIN_SUCCESS_RATE_FOR_COMPLETION <= 1
        assert 0 <= BatchCoordination.MAX_FAILURE_RATE_FOR_CONTINUATION < 1

        # Test timeout constants
        assert BatchCoordination.BATCH_PHASE_COMPLETION_TIMEOUT > 0
        assert BatchCoordination.INDIVIDUAL_ESSAY_PROCESSING_TIMEOUT > 0

        # Test retry configuration
        assert BatchCoordination.MAX_BATCH_RETRY_ATTEMPTS > 0
        assert BatchCoordination.RETRY_BACKOFF_SECONDS > 0
        assert BatchCoordination.RETRY_BACKOFF_MULTIPLIER > 1

    def test_query_limits_constants(self) -> None:
        """Test that QueryLimits constants are reasonable."""
        # Test batch limits
        assert QueryLimits.DEFAULT_BATCH_ESSAY_LIMIT > 0
        assert QueryLimits.MAX_PHASE_QUERY_RESULTS > 0

        # Test pagination limits
        assert QueryLimits.DEFAULT_PAGE_SIZE > 0
        assert QueryLimits.MAX_PAGE_SIZE >= QueryLimits.DEFAULT_PAGE_SIZE

        # Sanity check - limits should be reasonable for ELS operations
        assert QueryLimits.DEFAULT_BATCH_ESSAY_LIMIT <= 10000
        assert QueryLimits.MAX_PAGE_SIZE <= 1000


class TestConstantsErrorHandling:
    """Test suite for error handling in constants module."""

    @pytest.mark.parametrize(
        "invalid_phase",
        [
            "invalid_phase",
            "INVALID_PHASE",
            "student_matching",  # Valid enum but not ELS-coordinated
            "",
            "spellcheck_invalid",
        ],
    )
    def test_get_els_phase_statuses_error_handling_for_invalid_phases(
        self, invalid_phase: str
    ) -> None:
        """Test error handling for various invalid phase inputs."""
        with pytest.raises(ValueError) as exc_info:
            get_els_phase_statuses(invalid_phase)

        error_message = str(exc_info.value)
        # Error message should be informative
        assert len(error_message) > 10
        assert "phase" in error_message.lower()

    def test_get_els_phase_statuses_error_message_includes_valid_phases(self) -> None:
        """Test that error messages include list of valid ELS-coordinated phases."""
        with pytest.raises(ValueError) as exc_info:
            get_els_phase_statuses("invalid_phase")

        error_message = str(exc_info.value)

        # Should mention valid phases
        assert "ELS-coordinated phases" in error_message

        # Should include the actual valid phase names
        valid_phase_names = [phase.value for phase in ELS_PHASE_STATUS_MAPPING.keys()]
        for phase_name in valid_phase_names:
            assert phase_name in error_message

    def test_constants_consistency_validation(self) -> None:
        """Test internal consistency of constants module."""
        # EssayDefaults should reference MetadataKey constants
        assert (
            EssayDefaults.DEFAULT_PROCESSING_METADATA[MetadataKey.ENTITY_TYPE]
            == EssayDefaults.ENTITY_TYPE
        )
        assert (
            EssayDefaults.DEFAULT_PROCESSING_METADATA[MetadataKey.PROCESSING_ATTEMPT_COUNT]
            == EssayDefaults.INITIAL_PROCESSING_ATTEMPT_COUNT
        )

        # BatchCoordination success and failure rates should sum appropriately
        success_rate = BatchCoordination.MIN_SUCCESS_RATE_FOR_COMPLETION
        failure_rate = BatchCoordination.MAX_FAILURE_RATE_FOR_CONTINUATION
        # They should be complementary (allowing for some overlap/buffer)
        assert success_rate + failure_rate >= 0.8  # Some reasonable relationship

    def test_constants_documentation_completeness(self) -> None:
        """Test that key constants classes have proper structure."""
        constants_classes = [
            RepositoryOperation,
            MetadataKey,
            EssayDefaults,
            ServiceResultStatus,
            BatchCoordination,
            QueryLimits,
        ]

        for constants_class in constants_classes:
            # Each constants class should have at least some attributes
            class_attributes = [attr for attr in dir(constants_class) if not attr.startswith("_")]
            assert len(class_attributes) > 0, (
                f"{constants_class.__name__} should have public attributes"
            )
