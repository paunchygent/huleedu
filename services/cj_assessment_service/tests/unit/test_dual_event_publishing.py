"""Unit tests for dual event publishing logic.

This module tests the centralized dual event publishing function to ensure
it correctly creates and publishes two distinct events (thin to ELS, rich to RAS)
with proper data separation and field mapping.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent
from common_core.events.cj_assessment_events import GradeProjectionSummary
from common_core.status_enums import BatchStatus, ProcessingStage

from services.cj_assessment_service.cj_core_logic.dual_event_publisher import (
    publish_dual_assessment_events,
)
from services.cj_assessment_service.protocols import CJEventPublisherProtocol


class TestDualEventPublishing:
    """Tests for the publish_dual_assessment_events function."""

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
    def sample_grade_projections(self) -> GradeProjectionSummary:
        """Create sample grade projections with mixed student and anchor data."""
        return GradeProjectionSummary(
            projections_available=True,
            primary_grades={
                "student_1": "A",
                "student_2": "B",
                "ANCHOR_A_uuid": "A",
                "ANCHOR_B_uuid": "C",
            },
            confidence_labels={
                "student_1": "HIGH",
                "student_2": "MID",
                "ANCHOR_A_uuid": "HIGH",
                "ANCHOR_B_uuid": "HIGH",
            },
            confidence_scores={
                "student_1": 0.9,
                "student_2": 0.7,
                "ANCHOR_A_uuid": 1.0,
                "ANCHOR_B_uuid": 1.0,
            },
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
        )

    @pytest.mark.asyncio
    async def test_dual_event_separation_mixed_essays(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_grade_projections: GradeProjectionSummary,
        sample_batch_upload: Mock,
    ) -> None:
        """Test that ELS gets filtered rankings and RAS gets all rankings."""
        # Arrange
        rankings = [
            {"els_essay_id": "student_1", "score": 0.8, "rank": 1},
            {"els_essay_id": "ANCHOR_A_uuid", "score": 0.9, "rank": 2},
            {"els_essay_id": "student_2", "score": 0.6, "rank": 3},
            {"els_essay_id": "ANCHOR_B_uuid", "score": 0.5, "rank": 4},
        ]
        correlation_id = uuid4()

        # Act
        await publish_dual_assessment_events(
            rankings=rankings,
            grade_projections=sample_grade_projections,
            batch_upload=sample_batch_upload,
            event_publisher=mock_event_publisher,
            settings=test_settings,
            correlation_id=correlation_id,
            processing_started_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        )

        # Assert - ELS event
        els_call = mock_event_publisher.publish_assessment_completed.call_args
        assert els_call is not None
        els_envelope = els_call.kwargs["completion_data"]

        # ELS should only have student rankings
        assert len(els_envelope.data.rankings) == 2
        assert all(not r["els_essay_id"].startswith("ANCHOR_") for r in els_envelope.data.rankings)
        assert els_envelope.data.rankings[0]["els_essay_id"] == "student_1"
        assert els_envelope.data.rankings[1]["els_essay_id"] == "student_2"

        # Check grade projections are included
        assert els_envelope.data.grade_projections_summary == sample_grade_projections

        # Assert - RAS event
        ras_call = mock_event_publisher.publish_assessment_result.call_args
        assert ras_call is not None
        ras_envelope = ras_call.kwargs["result_data"]

        # RAS should have all essays
        assert len(ras_envelope.data.essay_results) == 4

        # Check anchor flags
        student_results = [r for r in ras_envelope.data.essay_results if not r["is_anchor"]]
        anchor_results = [r for r in ras_envelope.data.essay_results if r["is_anchor"]]
        assert len(student_results) == 2
        assert len(anchor_results) == 2

        # Check display names for anchors
        for anchor in anchor_results:
            assert anchor["display_name"] is not None
            assert anchor["display_name"].startswith("ANCHOR GRADE")

        # Check no display names for students
        for student in student_results:
            assert student["display_name"] is None

    @pytest.mark.asyncio
    async def test_anchor_grade_distribution_calculation(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_batch_upload: Mock,
    ) -> None:
        """Verify anchor_grade_distribution is correctly calculated."""
        # Arrange
        rankings = [
            {"els_essay_id": "ANCHOR_1", "score": 0.9, "rank": 1},
            {"els_essay_id": "ANCHOR_2", "score": 0.8, "rank": 2},
            {"els_essay_id": "ANCHOR_3", "score": 0.7, "rank": 3},
            {"els_essay_id": "student_1", "score": 0.6, "rank": 4},
        ]

        grade_projections = GradeProjectionSummary(
            projections_available=True,
            primary_grades={
                "ANCHOR_1": "A",
                "ANCHOR_2": "A",
                "ANCHOR_3": "B",
                "student_1": "C",
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

        # Assert
        ras_call = mock_event_publisher.publish_assessment_result.call_args
        ras_envelope = ras_call.kwargs["result_data"]

        # Check anchor_grade_distribution exists and is correct
        assert "anchor_grade_distribution" in ras_envelope.data.assessment_metadata
        distribution = ras_envelope.data.assessment_metadata["anchor_grade_distribution"]

        assert distribution == {
            "A": 2,  # Two A anchors
            "B": 1,  # One B anchor
            "C": 0,  # No C anchors (student_1 is not an anchor)
            "D": 0,
            "E": 0,
            "F": 0,
            "U": 0,
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "rankings,expected_status",
        [
            (
                [{"els_essay_id": "s1", "bradley_terry_score": 0.5, "rank": 1}],  # Has score
                BatchStatus.COMPLETED_SUCCESSFULLY,
            ),
            (
                [{"els_essay_id": "s1", "bradley_terry_score": None, "rank": 1}],  # No score
                BatchStatus.FAILED_CRITICALLY,
            ),
            (
                [],  # Empty rankings
                BatchStatus.FAILED_CRITICALLY,
            ),
            (
                [{"els_essay_id": "ANCHOR_1", "bradley_terry_score": 0.5, "rank": 1}],  # Only anchor
                BatchStatus.FAILED_CRITICALLY,  # No students
            ),
        ],
    )
    async def test_batch_status_selection(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_batch_upload: Mock,
        rankings: list[dict[str, Any]],
        expected_status: BatchStatus,
    ) -> None:
        """Test correct BatchStatus based on successful essay presence."""
        # Arrange
        grade_projections = GradeProjectionSummary(
            projections_available=False,
            primary_grades={},
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

        # Assert
        els_call = mock_event_publisher.publish_assessment_completed.call_args
        els_envelope = els_call.kwargs["completion_data"]
        assert els_envelope.data.status == expected_status

    @pytest.mark.asyncio
    async def test_field_mapping_correctness(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_batch_upload: Mock,
    ) -> None:
        """Verify all fields are mapped correctly between events."""
        # Arrange
        rankings = [
            {"els_essay_id": "student_1", "bradley_terry_score": 0.85, "rank": 1},
            {"els_essay_id": "ANCHOR_A", "bradley_terry_score": 0.95, "rank": 2},
        ]

        grade_projections = GradeProjectionSummary(
            projections_available=True,
            primary_grades={"student_1": "B", "ANCHOR_A": "A"},
            confidence_labels={"student_1": "HIGH", "ANCHOR_A": "HIGH"},
            confidence_scores={"student_1": 0.88, "ANCHOR_A": 1.0},
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

        # Assert - Check RAS event field mapping
        ras_call = mock_event_publisher.publish_assessment_result.call_args
        ras_envelope = ras_call.kwargs["result_data"]

        student_result = next(
            r for r in ras_envelope.data.essay_results if r["essay_id"] == "student_1"
        )
        anchor_result = next(
            r for r in ras_envelope.data.essay_results if r["essay_id"] == "ANCHOR_A"
        )

        # Check student fields
        assert student_result["bt_score"] == 0.85  # score → bt_score
        assert student_result["rank"] == 1
        assert student_result["letter_grade"] == "B"
        assert student_result["confidence_score"] == 0.88
        assert student_result["confidence_label"] == "HIGH"
        assert student_result["is_anchor"] is False
        assert student_result["display_name"] is None
        assert 0.0 <= student_result["normalized_score"] <= 1.0

        # Check anchor fields
        assert anchor_result["bt_score"] == 0.95
        assert anchor_result["is_anchor"] is True
        assert anchor_result["display_name"] == "ANCHOR GRADE A"
        assert anchor_result["letter_grade"] == "A"

    @pytest.mark.asyncio
    async def test_course_code_enum_handling(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
    ) -> None:
        """Test CourseCode enum is converted to string value."""
        # Arrange
        batch_upload = Mock(
            bos_batch_id="bos_123",
            id="cj_456",
            assignment_id="assignment_789",
            course_code=CourseCode.SV2,  # Enum value
            created_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        )

        # Act
        await publish_dual_assessment_events(
            rankings=[],
            grade_projections=GradeProjectionSummary(
                projections_available=False,
                primary_grades={},
                confidence_labels={},
                confidence_scores={},
            ),
            batch_upload=batch_upload,
            event_publisher=mock_event_publisher,
            settings=test_settings,
            correlation_id=uuid4(),
        )

        # Assert
        ras_call = mock_event_publisher.publish_assessment_result.call_args
        ras_envelope = ras_call.kwargs["result_data"]

        # Course code should be string value, not enum
        assert ras_envelope.data.assessment_metadata["course_code"] == "SV2"

    @pytest.mark.asyncio
    async def test_processing_duration_calculation(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_batch_upload: Mock,
    ) -> None:
        """Verify processing_duration_seconds is calculated correctly."""
        # Arrange
        processing_started_at = datetime.now(UTC)

        # Act
        await publish_dual_assessment_events(
            rankings=[],
            grade_projections=GradeProjectionSummary(
                projections_available=False,
                primary_grades={},
                confidence_labels={},
                confidence_scores={},
            ),
            batch_upload=sample_batch_upload,
            event_publisher=mock_event_publisher,
            settings=test_settings,
            correlation_id=uuid4(),
            processing_started_at=processing_started_at,
        )

        # Assert
        ras_call = mock_event_publisher.publish_assessment_result.call_args
        ras_envelope = ras_call.kwargs["result_data"]

        # Duration should be very small (function executes quickly)
        duration = ras_envelope.data.assessment_metadata["processing_duration_seconds"]
        assert 0.0 <= duration < 5.0  # Should complete within 5 seconds

    @pytest.mark.asyncio
    async def test_correlation_id_propagation(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_batch_upload: Mock,
    ) -> None:
        """Ensure same correlation_id used for both events."""
        # Arrange
        correlation_id = uuid4()

        # Act
        await publish_dual_assessment_events(
            rankings=[],
            grade_projections=GradeProjectionSummary(
                projections_available=False,
                primary_grades={},
                confidence_labels={},
                confidence_scores={},
            ),
            batch_upload=sample_batch_upload,
            event_publisher=mock_event_publisher,
            settings=test_settings,
            correlation_id=correlation_id,
        )

        # Assert
        els_call = mock_event_publisher.publish_assessment_completed.call_args
        ras_call = mock_event_publisher.publish_assessment_result.call_args

        # Both should receive same correlation_id
        assert els_call.kwargs["correlation_id"] == correlation_id
        assert ras_call.kwargs["correlation_id"] == correlation_id

        # Check envelopes also have correct correlation_id
        els_envelope = els_call.kwargs["completion_data"]
        ras_envelope = ras_call.kwargs["result_data"]
        assert els_envelope.correlation_id == correlation_id
        assert ras_envelope.correlation_id == correlation_id

    @pytest.mark.asyncio
    async def test_only_students_no_anchors(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_batch_upload: Mock,
    ) -> None:
        """Test handling when there are no anchor essays."""
        # Arrange
        rankings = [
            {"els_essay_id": "student_1", "score": 0.8, "rank": 1},
            {"els_essay_id": "student_2", "score": 0.6, "rank": 2},
        ]

        grade_projections = GradeProjectionSummary(
            projections_available=False,  # No anchors
            primary_grades={"student_1": "U", "student_2": "U"},
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

        # Assert
        ras_call = mock_event_publisher.publish_assessment_result.call_args
        ras_envelope = ras_call.kwargs["result_data"]

        # anchor_grade_distribution should be empty dict
        assert ras_envelope.data.assessment_metadata["anchor_grade_distribution"] == {}
        assert ras_envelope.data.assessment_metadata["calibration_method"] == "default"
        assert ras_envelope.data.assessment_metadata["anchor_essays_used"] == 0

    @pytest.mark.asyncio
    async def test_event_metadata_completeness(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_batch_upload: Mock,
    ) -> None:
        """Test that all required metadata fields are present in both events."""
        # Arrange
        rankings = [{"els_essay_id": "student_1", "score": 0.8, "rank": 1}]
        grade_projections = GradeProjectionSummary(
            projections_available=False,
            primary_grades={"student_1": "B"},
            confidence_labels={"student_1": "MID"},
            confidence_scores={"student_1": 0.75},
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

        # Assert - ELS event
        els_call = mock_event_publisher.publish_assessment_completed.call_args
        els_envelope = els_call.kwargs["completion_data"]

        assert els_envelope.event_type == "cj_assessment.completed.v1"
        assert els_envelope.source_service == "cj_assessment_service"
        assert els_envelope.data.event_name == ProcessingEvent.CJ_ASSESSMENT_COMPLETED
        assert els_envelope.data.entity_id == "bos_123"
        assert els_envelope.data.cj_assessment_job_id == "cj_456"
        assert els_envelope.data.system_metadata.processing_stage == ProcessingStage.COMPLETED

        # Assert - RAS event
        ras_call = mock_event_publisher.publish_assessment_result.call_args
        ras_envelope = ras_call.kwargs["result_data"]

        assert ras_envelope.event_type == "huleedu.assessment.results.v1"
        assert ras_envelope.source_service == "cj_assessment_service"
        assert ras_envelope.data.event_name == ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED
        assert ras_envelope.data.batch_id == "bos_123"
        assert ras_envelope.data.cj_assessment_job_id == "cj_456"
        assert ras_envelope.data.assessment_method == "cj_assessment"
        assert ras_envelope.data.model_used == "gpt-4"
        assert ras_envelope.data.model_provider == "openai"
        assert ras_envelope.data.model_version == "20240101"

        # Check assessment_metadata has all expected fields
        metadata = ras_envelope.data.assessment_metadata
        assert "anchor_essays_used" in metadata
        assert "calibration_method" in metadata
        assert "anchor_grade_distribution" in metadata
        assert "comparison_count" in metadata
        assert "processing_duration_seconds" in metadata
        assert "llm_temperature" in metadata
        assert metadata["llm_temperature"] == 0.7
        assert metadata["assignment_id"] == "assignment_789"
        assert metadata["course_code"] == "ENG5"

    @pytest.mark.asyncio
    async def test_anchor_identification_and_separation(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_batch_upload: Mock,
    ) -> None:
        """Test that essays are correctly separated between ELS and RAS events
        with proper flagging."""
        # Arrange - Mix of student and anchor essays with various ID formats
        rankings = [
            # Student essays with different ID patterns
            {"els_essay_id": "student_001", "score": 0.8, "rank": 1},
            {"els_essay_id": "essay_uuid_123", "score": 0.7, "rank": 2},
            {"els_essay_id": "regular_id", "score": 0.6, "rank": 3},
            {"els_essay_id": "contains_ANCHOR_but_not_prefix", "score": 0.5, "rank": 7},
            # Anchor essays with different formats
            {"els_essay_id": "ANCHOR_A_uuid_123", "score": 0.9, "rank": 4},
            {"els_essay_id": "ANCHOR_B_456", "score": 0.85, "rank": 5},
            {"els_essay_id": "ANCHOR_COMPLEX_ID_789", "score": 0.75, "rank": 6},
        ]

        grade_projections = GradeProjectionSummary(
            projections_available=True,
            primary_grades={
                "student_001": "A",
                "essay_uuid_123": "B",
                "regular_id": "C",
                "contains_ANCHOR_but_not_prefix": "D",
                "ANCHOR_A_uuid_123": "A",
                "ANCHOR_B_456": "B",
                "ANCHOR_COMPLEX_ID_789": "C",
            },
            confidence_labels={
                "student_001": "HIGH",
                "essay_uuid_123": "MID",
                "regular_id": "HIGH",
                "contains_ANCHOR_but_not_prefix": "LOW",
                "ANCHOR_A_uuid_123": "HIGH",
                "ANCHOR_B_456": "HIGH",
                "ANCHOR_COMPLEX_ID_789": "MID",
            },
            confidence_scores={
                "student_001": 0.9,
                "essay_uuid_123": 0.75,
                "regular_id": 0.85,
                "contains_ANCHOR_but_not_prefix": 0.6,
                "ANCHOR_A_uuid_123": 1.0,
                "ANCHOR_B_456": 0.95,
                "ANCHOR_COMPLEX_ID_789": 0.8,
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

        # Assert - Verify behavioral outcomes
        els_call = mock_event_publisher.publish_assessment_completed.call_args
        ras_call = mock_event_publisher.publish_assessment_result.call_args

        els_envelope = els_call.kwargs["completion_data"]
        ras_envelope = ras_call.kwargs["result_data"]

        # ELS event should contain subset of essays (students only)
        assert len(els_envelope.data.rankings) == 4
        els_essay_ids = {r["els_essay_id"] for r in els_envelope.data.rankings}

        # RAS event should contain all essays with anchor flags
        assert len(ras_envelope.data.essay_results) == 7

        # Separate RAS results by anchor flag
        student_results = [r for r in ras_envelope.data.essay_results if not r["is_anchor"]]
        anchor_results = [r for r in ras_envelope.data.essay_results if r["is_anchor"]]

        # Verify the separation produced the expected counts
        assert len(student_results) == 4
        assert len(anchor_results) == 3

        # Verify all student essays appear in ELS event
        student_ids_in_ras = {r["essay_id"] for r in student_results}
        assert els_essay_ids == student_ids_in_ras

        # Verify anchor-specific attributes are set correctly
        for anchor in anchor_results:
            assert anchor["is_anchor"] is True
            assert anchor["display_name"] is not None

        # Verify student-specific attributes are set correctly
        for student in student_results:
            assert student["is_anchor"] is False
            assert student["display_name"] is None

        # Verify all original essays are accounted for in RAS
        all_ras_ids = {r["essay_id"] for r in ras_envelope.data.essay_results}
        all_original_ids = {r["els_essay_id"] for r in rankings}
        assert all_ras_ids == all_original_ids

    @pytest.mark.asyncio
    async def test_comprehensive_anchor_grade_distribution(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_batch_upload: Mock,
    ) -> None:
        """Test comprehensive anchor grade distribution calculation across all grade levels."""
        # Arrange - Design data to comprehensively test grade distribution
        rankings = [
            # Student essays (should NOT affect anchor distribution)
            {"els_essay_id": "student_excellent", "score": 0.95, "rank": 1},
            {"els_essay_id": "student_good", "score": 0.75, "rank": 2},
            {"els_essay_id": "student_poor", "score": 0.3, "rank": 10},
            # Anchor essays with diverse grade assignments
            {"els_essay_id": "ANCHOR_A_top", "score": 0.9, "rank": 3},  # Grade A
            {"els_essay_id": "ANCHOR_A_second", "score": 0.88, "rank": 4},  # Grade A
            {"els_essay_id": "ANCHOR_B_single", "score": 0.8, "rank": 5},  # Grade B
            {"els_essay_id": "ANCHOR_C_first", "score": 0.7, "rank": 6},  # Grade C
            {"els_essay_id": "ANCHOR_C_second", "score": 0.68, "rank": 7},  # Grade C
            {"els_essay_id": "ANCHOR_C_third", "score": 0.65, "rank": 8},  # Grade C
            {"els_essay_id": "ANCHOR_D_only", "score": 0.5, "rank": 9},  # Grade D
            {"els_essay_id": "ANCHOR_U_failing", "score": 0.2, "rank": 11},  # Grade U
        ]

        # Create grade projections with specific grade assignments
        grade_projections = GradeProjectionSummary(
            projections_available=True,
            primary_grades={
                # Students get various grades but shouldn't affect anchor distribution
                "student_excellent": "A",
                "student_good": "B",
                "student_poor": "U",
                # Anchors with intentional grade distribution: A=2, B=1, C=3, D=1, U=1
                "ANCHOR_A_top": "A",
                "ANCHOR_A_second": "A",
                "ANCHOR_B_single": "B",
                "ANCHOR_C_first": "C",
                "ANCHOR_C_second": "C",
                "ANCHOR_C_third": "C",
                "ANCHOR_D_only": "D",
                "ANCHOR_U_failing": "U",
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

        # Assert - Verify behavioral outcome in RAS event
        ras_call = mock_event_publisher.publish_assessment_result.call_args
        ras_envelope = ras_call.kwargs["result_data"]

        # Verify anchor_grade_distribution is present and correct
        assert "anchor_grade_distribution" in ras_envelope.data.assessment_metadata
        distribution = ras_envelope.data.assessment_metadata["anchor_grade_distribution"]

        # Verify expected grade distribution (based on anchor essays only)
        expected_distribution = {
            "A": 2,  # ANCHOR_A_top, ANCHOR_A_second
            "B": 1,  # ANCHOR_B_single
            "C": 3,  # ANCHOR_C_first, ANCHOR_C_second, ANCHOR_C_third
            "D": 1,  # ANCHOR_D_only
            "E": 0,  # No E grade anchors
            "F": 0,  # No F grade anchors
            "U": 1,  # ANCHOR_U_failing
        }

        assert distribution == expected_distribution

        # Verify all standard grades are represented in the distribution
        standard_grades = ["A", "B", "C", "D", "E", "F", "U"]
        for grade in standard_grades:
            assert grade in distribution

        # Verify total anchor count matches expected
        total_anchors = sum(distribution.values())
        assert total_anchors == 8  # 8 anchor essays

        # Verify RAS metadata indicates anchors were used
        assert ras_envelope.data.assessment_metadata["anchor_essays_used"] == 8
        assert ras_envelope.data.assessment_metadata["calibration_method"] == "anchor"
