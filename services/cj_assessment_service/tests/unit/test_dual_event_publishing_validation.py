"""Validation, error handling, and data resilience tests for dual event publishing.

This module tests field validation, data type correctness, error handling,
and resilience of the dual event publishing system against edge cases and invalid data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.events.cj_assessment_events import GradeProjectionSummary
from common_core.status_enums import BatchStatus

from services.cj_assessment_service.cj_core_logic.dual_event_publisher import (
    publish_dual_assessment_events,
)
from services.cj_assessment_service.protocols import CJEventPublisherProtocol


class TestDualEventPublishingValidation:
    """Validation and error handling tests for dual event publishing."""

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher that captures both events."""
        publisher = AsyncMock(spec=CJEventPublisherProtocol)
        publisher.publish_assessment_completed = AsyncMock()
        publisher.publish_assessment_result = AsyncMock()
        return publisher

    @pytest.fixture
    def test_settings(self) -> Mock:
        """Create test settings with required fields."""
        return Mock(
            CJ_ASSESSMENT_COMPLETED_TOPIC="cj_assessment.completed.v1",
            ASSESSMENT_RESULT_TOPIC="huleedu.assessment.results.v1",
            SERVICE_NAME="cj_assessment_service",
            DEFAULT_LLM_MODEL="gpt-4",
            DEFAULT_LLM_PROVIDER=Mock(value="openai"),
            DEFAULT_LLM_MODEL_VERSION="20240101",
            DEFAULT_LLM_TEMPERATURE=0.7,
        )

    @pytest.fixture
    def sample_batch_upload(self) -> Mock:
        """Create sample batch upload with metadata."""
        return Mock(
            bos_batch_id="bos_123",
            id="cj_456",
            assignment_id="assignment_789",
            course_code=CourseCode.ENG5,
            created_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
            # Identity fields for ResourceConsumptionV1 publishing
            user_id="test-user-789",
            org_id=None,  # Test scenario without org
        )

    @pytest.mark.asyncio
    async def test_field_types_and_normalized_score_calculation(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_batch_upload: Mock,
    ) -> None:
        """Verify all RAS event fields have correct types and normalized scores
        are calculated properly."""
        # Arrange - Test with extreme score values to verify normalization
        rankings = [
            # Student essays with various score ranges
            {"els_essay_id": "student_high", "bradley_terry_score": 0.95, "rank": 1},
            {"els_essay_id": "student_mid", "bradley_terry_score": 0.5, "rank": 2},
            {"els_essay_id": "student_low", "bradley_terry_score": 0.05, "rank": 3},
            {"els_essay_id": "student_zero", "bradley_terry_score": 0.0, "rank": 4},
            # Anchor essays with edge case scores
            {"els_essay_id": "ANCHOR_perfect", "bradley_terry_score": 1.0, "rank": 5},
            {"els_essay_id": "ANCHOR_minimal", "bradley_terry_score": 0.01, "rank": 6},
        ]

        grade_projections = GradeProjectionSummary(
            projections_available=True,
            primary_grades={
                "student_high": "A",
                "student_mid": "C",
                "student_low": "E",
                "student_zero": "U",
                "ANCHOR_perfect": "A",
                "ANCHOR_minimal": "U",
            },
            confidence_labels={
                "student_high": "HIGH",
                "student_mid": "MID",
                "student_low": "LOW",
                "student_zero": "LOW",
                "ANCHOR_perfect": "HIGH",
                "ANCHOR_minimal": "LOW",
            },
            confidence_scores={
                "student_high": 0.95,
                "student_mid": 0.6,
                "student_low": 0.4,
                "student_zero": 0.1,
                "ANCHOR_perfect": 1.0,
                "ANCHOR_minimal": 0.2,
            },
        )

        # Act
        await publish_dual_assessment_events(
            rankings=rankings,
            grade_projections=grade_projections,
            batch_upload=sample_batch_upload,
            event_publisher=mock_event_publisher,
            settings=test_settings,
            correlation_id=uuid4(),
        )

        # Assert - Verify RAS event field types and values
        ras_call = mock_event_publisher.publish_assessment_result.call_args
        ras_envelope = ras_call.kwargs["result_data"]

        # Verify all essay results have correct field types
        for result in ras_envelope.data.essay_results:
            # String fields
            assert isinstance(result.essay_id, str)
            assert isinstance(result.letter_grade, str)
            assert isinstance(result.confidence_label, str)

            # Float fields
            assert isinstance(result.bt_score, (int, float))
            assert isinstance(result.confidence_score, (int, float))
            assert isinstance(result.normalized_score, (int, float))

            # Integer field
            assert isinstance(result.rank, int)

            # Boolean field
            assert isinstance(result.is_anchor, bool)

            # Nullable string field (only anchors have display names)
            if result.is_anchor:
                assert isinstance(result.display_name, str)
            else:
                assert result.display_name is None

        # Verify normalized_score is always in valid range
        for result in ras_envelope.data.essay_results:
            normalized_score = result.normalized_score
            assert 0.0 <= normalized_score <= 1.0

        # Verify assessment_metadata field types
        metadata = ras_envelope.data.assessment_metadata
        assert isinstance(metadata["anchor_essays_used"], int)
        assert isinstance(metadata["calibration_method"], str)
        assert isinstance(metadata["anchor_grade_distribution"], dict)
        assert isinstance(metadata["comparison_count"], int)
        assert isinstance(metadata["processing_duration_seconds"], (int, float))
        assert isinstance(metadata["llm_temperature"], (int, float))

    @pytest.mark.asyncio
    async def test_display_name_formats_for_all_grades(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_batch_upload: Mock,
    ) -> None:
        """Verify anchor display names follow correct format for all grade levels."""
        # Arrange - Create anchors with each possible grade
        rankings = [
            # Student essay (should not get display name)
            {"els_essay_id": "student_1", "bradley_terry_score": 0.8, "rank": 1},
            # Anchor essays with each grade level
            {"els_essay_id": "ANCHOR_A", "bradley_terry_score": 0.9, "rank": 2},
            {"els_essay_id": "ANCHOR_B", "bradley_terry_score": 0.85, "rank": 3},
            {"els_essay_id": "ANCHOR_C", "bradley_terry_score": 0.75, "rank": 4},
            {"els_essay_id": "ANCHOR_D", "bradley_terry_score": 0.6, "rank": 5},
            {"els_essay_id": "ANCHOR_E", "bradley_terry_score": 0.45, "rank": 6},
            {"els_essay_id": "ANCHOR_F", "bradley_terry_score": 0.3, "rank": 7},
            {"els_essay_id": "ANCHOR_U", "bradley_terry_score": 0.1, "rank": 8},
        ]

        grade_projections = GradeProjectionSummary(
            projections_available=True,
            primary_grades={
                "student_1": "B",
                "ANCHOR_A": "A",
                "ANCHOR_B": "B",
                "ANCHOR_C": "C",
                "ANCHOR_D": "D",
                "ANCHOR_E": "E",
                "ANCHOR_F": "F",
                "ANCHOR_U": "U",
            },
            confidence_labels={},
            confidence_scores={},
        )

        # Act
        await publish_dual_assessment_events(
            rankings=rankings,
            grade_projections=grade_projections,
            batch_upload=sample_batch_upload,
            event_publisher=mock_event_publisher,
            settings=test_settings,
            correlation_id=uuid4(),
        )

        # Assert - Verify display name formats
        ras_call = mock_event_publisher.publish_assessment_result.call_args
        ras_envelope = ras_call.kwargs["result_data"]

        # Separate results by type
        student_results = [r for r in ras_envelope.data.essay_results if not r.is_anchor]
        anchor_results = [r for r in ras_envelope.data.essay_results if r.is_anchor]

        # Verify student has no display name
        assert len(student_results) == 1
        assert student_results[0].display_name is None

        # Verify each anchor has correct display name format
        assert len(anchor_results) == 7
        expected_display_names = {
            "ANCHOR_A": "ANCHOR GRADE A",
            "ANCHOR_B": "ANCHOR GRADE B",
            "ANCHOR_C": "ANCHOR GRADE C",
            "ANCHOR_D": "ANCHOR GRADE D",
            "ANCHOR_E": "ANCHOR GRADE E",
            "ANCHOR_F": "ANCHOR GRADE F",
            "ANCHOR_U": "ANCHOR GRADE U",
        }

        for result in anchor_results:
            essay_id = result.essay_id
            expected_name = expected_display_names[essay_id]
            assert result.display_name == expected_name

    @pytest.mark.asyncio
    async def test_data_resilience_with_missing_confidence_data(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_batch_upload: Mock,
    ) -> None:
        """Test system handles missing or incomplete confidence data gracefully."""
        # Arrange - Mix of complete and incomplete confidence data
        rankings = [
            {"els_essay_id": "student_complete", "bradley_terry_score": 0.8, "rank": 1},
            {"els_essay_id": "student_partial", "bradley_terry_score": 0.7, "rank": 2},
            {"els_essay_id": "ANCHOR_A", "bradley_terry_score": 0.9, "rank": 3},
        ]

        # Grade projections with missing confidence data for some essays
        grade_projections = GradeProjectionSummary(
            projections_available=True,
            primary_grades={
                "student_complete": "A",
                "student_partial": "B",
                "ANCHOR_A": "A",
            },
            confidence_labels={
                "student_complete": "HIGH",
                # student_partial missing confidence_label
                "ANCHOR_A": "HIGH",
            },
            confidence_scores={
                "student_complete": 0.9,
                # student_partial missing confidence_score
                "ANCHOR_A": 1.0,
            },
        )

        # Act - Should not raise exceptions
        await publish_dual_assessment_events(
            rankings=rankings,
            grade_projections=grade_projections,
            batch_upload=sample_batch_upload,
            event_publisher=mock_event_publisher,
            settings=test_settings,
            correlation_id=uuid4(),
        )

        # Assert - Events should be published successfully
        ras_call = mock_event_publisher.publish_assessment_result.call_args
        ras_envelope = ras_call.kwargs["result_data"]

        # Verify all essays are included despite missing confidence data
        assert len(ras_envelope.data.essay_results) == 3

        # Find the essay with partial confidence data
        partial_result = next(
            r for r in ras_envelope.data.essay_results if r.essay_id == "student_partial"
        )

        # Verify system provides default values for missing confidence data
        # (The exact default values depend on implementation, but should be reasonable)
        assert partial_result.confidence_label is not None
        assert isinstance(partial_result.confidence_score, (int, float))
        assert 0.0 <= partial_result.confidence_score <= 1.0

    @pytest.mark.asyncio
    async def test_data_resilience_with_null_scores(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_batch_upload: Mock,
    ) -> None:
        """Test system handles null/None scores in rankings gracefully."""
        # Arrange - Mix of valid and null scores
        rankings: list[dict[str, Any]] = [
            {"els_essay_id": "student_valid", "bradley_terry_score": 0.8, "rank": 1},
            {"els_essay_id": "student_null", "bradley_terry_score": None, "rank": 2},  # Null score
            {"els_essay_id": "ANCHOR_A", "bradley_terry_score": 0.9, "rank": 3},
        ]

        grade_projections = GradeProjectionSummary(
            projections_available=True,
            primary_grades={
                "student_valid": "A",
                "student_null": "U",  # Failed essay
                "ANCHOR_A": "A",
            },
            confidence_labels={
                "student_valid": "HIGH",
                "student_null": "LOW",
                "ANCHOR_A": "HIGH",
            },
            confidence_scores={
                "student_valid": 0.9,
                "student_null": 0.1,
                "ANCHOR_A": 1.0,
            },
        )

        # Act - Should handle null scores gracefully
        await publish_dual_assessment_events(
            rankings=rankings,
            grade_projections=grade_projections,
            batch_upload=sample_batch_upload,
            event_publisher=mock_event_publisher,
            settings=test_settings,
            correlation_id=uuid4(),
        )

        # Assert - Verify proper handling of null scores
        els_call = mock_event_publisher.publish_assessment_completed.call_args
        ras_call = mock_event_publisher.publish_assessment_result.call_args

        els_envelope = els_call.kwargs["completion_data"]
        ras_envelope = ras_call.kwargs["result_data"]

        # ELS should recognize null score as failed essay
        assert (
            els_envelope.data.status == BatchStatus.COMPLETED_SUCCESSFULLY
        )  # Still has 1 successful

        # RAS should include all essays, handling null scores appropriately
        assert len(ras_envelope.data.essay_results) == 3

        null_score_result = next(
            r for r in ras_envelope.data.essay_results if r.essay_id == "student_null"
        )

        # Verify null score is converted to 0.0 (correct behavior for failed essays)
        assert null_score_result.bt_score == 0.0  # Null scores become 0.0 for Pydantic validation
        # normalized_score should still be calculated (likely 0.0 for failed essays)
        assert isinstance(null_score_result.normalized_score, (int, float))
        assert 0.0 <= null_score_result.normalized_score <= 1.0
