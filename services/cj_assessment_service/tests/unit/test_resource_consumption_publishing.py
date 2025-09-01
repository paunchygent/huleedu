"""Unit tests for ResourceConsumptionV1 event publishing in dual_event_publisher.py.

This module tests the resource consumption event publishing logic within the
publish_dual_assessment_events function, focusing on identity extraction,
event creation, validation, and error handling for entitlements credit tracking.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.cj_assessment_events import GradeProjectionSummary
from common_core.events.envelope import EventEnvelope
from common_core.events.resource_consumption_events import ResourceConsumptionV1

from services.cj_assessment_service.cj_core_logic.dual_event_publisher import (
    DualEventPublishingData,
    publish_dual_assessment_events,
)
from services.cj_assessment_service.protocols import CJEventPublisherProtocol


class TestResourceConsumptionPublishing:
    """Tests for ResourceConsumptionV1 event publishing within dual event publisher."""

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher with resource consumption publishing capability."""
        publisher = AsyncMock(spec=CJEventPublisherProtocol)
        publisher.publish_assessment_completed = AsyncMock()
        publisher.publish_assessment_result = AsyncMock()
        publisher.publish_resource_consumption = AsyncMock()
        return publisher

    @pytest.fixture
    def test_settings(self) -> Mock:
        """Create test settings with required fields for event publishing."""
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
        """Create minimal grade projections for resource consumption testing."""
        return GradeProjectionSummary(
            projections_available=True,
            primary_grades={
                "student_1": "A",
                "student_2": "B",
            },
            confidence_labels={
                "student_1": "HIGH",
                "student_2": "MID",
            },
            confidence_scores={
                "student_1": 0.9,
                "student_2": 0.7,
            },
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_id,org_id,expected_user_str,expected_org_str",
        [
            ("user-123", "org-456", "user-123", "org-456"),  # Standard case
            ("solo-user-789", None, "solo-user-789", None),  # No org
            (
                "användare-åäö",
                "organisation-ÅÄÖ",
                "användare-åäö",
                "organisation-ÅÄÖ",
            ),  # Swedish chars
            ("12345", "67890", "12345", "67890"),  # Numeric IDs
        ],
    )
    async def test_identity_extraction_and_conversion(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_grade_projections: GradeProjectionSummary,
        user_id: str,
        org_id: str | None,
        expected_user_str: str,
        expected_org_str: str | None,
    ) -> None:
        """Test identity field extraction from publishing_data and proper string conversion."""
        # Arrange
        publishing_data = DualEventPublishingData(
            bos_batch_id="bos_test_123",
            cj_batch_id="cj_456",
            assignment_id="assignment_789",
            course_code=CourseCode.ENG5.value,
            created_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
            user_id=user_id,
            org_id=org_id,
        )
        rankings = [
            {"els_essay_id": "student_1", "bradley_terry_score": 0.8, "rank": 1},
            {"els_essay_id": "student_2", "bradley_terry_score": 0.7, "rank": 2},
        ]

        # Act
        await publish_dual_assessment_events(
            rankings=rankings,
            grade_projections=sample_grade_projections,
            publishing_data=publishing_data,
            event_publisher=mock_event_publisher,
            settings=test_settings,
            correlation_id=uuid4(),
        )

        # Assert
        resource_call = mock_event_publisher.publish_resource_consumption.call_args
        assert resource_call is not None
        resource_envelope = resource_call.kwargs["resource_event"]
        assert isinstance(resource_envelope, EventEnvelope)
        assert isinstance(resource_envelope.data, ResourceConsumptionV1)
        assert resource_envelope.data.user_id == expected_user_str
        assert resource_envelope.data.org_id == expected_org_str

    @pytest.mark.asyncio
    @pytest.mark.parametrize("user_id_scenario", ["missing", "none"])
    async def test_user_id_validation_error_handling(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_grade_projections: GradeProjectionSummary,
        user_id_scenario: str,
    ) -> None:
        """Test ValueError handling when user_id is None or missing from publishing_data."""
        # DualEventPublishingData enforces user_id as required, so we test by using a Mock
        # to simulate the old batch_upload interface that could have None/missing user_id
        if user_id_scenario == "none":
            # Create mock publishing data with None user_id to test the validation
            publishing_data = Mock(
                bos_batch_id="bos_no_user",
                cj_batch_id="cj_789",
                assignment_id="assignment_123",
                course_code="SV2",
                created_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
                org_id="test-org",
                user_id=None,  # Simulating None user_id
            )
        else:  # missing scenario
            # Create mock without user_id attribute
            publishing_data = Mock(
                bos_batch_id="bos_no_user",
                cj_batch_id="cj_789",
                assignment_id="assignment_123",
                course_code="SV2",
                created_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
                org_id="test-org",
                # user_id is missing - will trigger AttributeError
            )
            if hasattr(publishing_data, "user_id"):
                delattr(publishing_data, "user_id")

        rankings = [{"els_essay_id": "student_1", "bradley_terry_score": 0.8, "rank": 1}]

        await publish_dual_assessment_events(
            rankings=rankings,
            grade_projections=sample_grade_projections,
            publishing_data=publishing_data,
            event_publisher=mock_event_publisher,
            settings=test_settings,
            correlation_id=uuid4(),
        )

        # Verify other events were still published but resource consumption was not
        mock_event_publisher.publish_assessment_completed.assert_called_once()
        mock_event_publisher.publish_assessment_result.assert_called_once()
        mock_event_publisher.publish_resource_consumption.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "student_count,expected_comparisons",
        [
            # Standard comparison calculation: n * (n-1) / 2
            (2, 1),  # 2 * 1 / 2 = 1 comparison
            (3, 3),  # 3 * 2 / 2 = 3 comparisons
            (4, 6),  # 4 * 3 / 2 = 6 comparisons
            (5, 10),  # 5 * 4 / 2 = 10 comparisons
            (10, 45),  # 10 * 9 / 2 = 45 comparisons
            # Edge cases
            (1, 0),  # 1 * 0 / 2 = 0 comparisons (single essay)
            (0, 0),  # 0 * -1 / 2 = 0 comparisons (no essays)
        ],
    )
    async def test_quantity_calculation_for_estimated_comparisons(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        student_count: int,
        expected_comparisons: int,
    ) -> None:
        """Test quantity calculation uses student-only essays to avoid anchor inflation."""
        # Arrange
        publishing_data = DualEventPublishingData(
            bos_batch_id="bos_quantity_test",
            cj_batch_id="cj_calc",
            assignment_id="assignment_calc",
            course_code=CourseCode.ENG5.value,
            created_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
            user_id="calc-user-123",
            org_id="calc-org-456",
        )

        # Create rankings with only student essays (no anchors)
        rankings = [
            {
                "els_essay_id": f"student_{i + 1}",
                "bradley_terry_score": 0.8 - (i * 0.1),
                "rank": i + 1,
            }
            for i in range(student_count)
        ]

        # Create matching grade projections
        grade_projections = GradeProjectionSummary(
            projections_available=True,
            primary_grades={f"student_{i + 1}": "B" for i in range(student_count)},
            confidence_labels={f"student_{i + 1}": "MID" for i in range(student_count)},
            confidence_scores={f"student_{i + 1}": 0.7 for i in range(student_count)},
        )

        # Act
        await publish_dual_assessment_events(
            rankings=rankings,
            grade_projections=grade_projections,
            publishing_data=publishing_data,
            event_publisher=mock_event_publisher,
            settings=test_settings,
            correlation_id=uuid4(),
        )

        # Assert
        if student_count > 0 and expected_comparisons >= 0:
            resource_call = mock_event_publisher.publish_resource_consumption.call_args
            assert resource_call is not None

            resource_envelope = resource_call.kwargs["resource_event"]
            assert resource_envelope.data.quantity == expected_comparisons
        else:
            # For edge cases where no valid user_id or no essays
            mock_event_publisher.publish_resource_consumption.assert_called()

    @pytest.mark.asyncio
    async def test_anchor_essays_excluded_from_quantity_calculation(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
    ) -> None:
        """Test that anchor essays are excluded from comparison quantity calculation."""
        # Arrange
        publishing_data = DualEventPublishingData(
            bos_batch_id="bos_anchor_exclusion",
            cj_batch_id="cj_exclusion",
            assignment_id="assignment_exclusion",
            course_code=CourseCode.ENG5.value,
            created_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
            user_id="exclusion-user-123",
            org_id="exclusion-org-456",
        )

        # Mix of 3 student essays and 2 anchor essays
        rankings = [
            {"els_essay_id": "student_1", "bradley_terry_score": 0.9, "rank": 1},
            {"els_essay_id": "student_2", "bradley_terry_score": 0.8, "rank": 2},
            {"els_essay_id": "ANCHOR_A", "bradley_terry_score": 0.85, "rank": 3},
            {"els_essay_id": "student_3", "bradley_terry_score": 0.7, "rank": 4},
            {"els_essay_id": "ANCHOR_B", "bradley_terry_score": 0.75, "rank": 5},
        ]

        grade_projections = GradeProjectionSummary(
            projections_available=True,
            primary_grades={
                "student_1": "A",
                "student_2": "B",
                "student_3": "C",
                "ANCHOR_A": "A",
                "ANCHOR_B": "B",
            },
            confidence_labels={
                "student_1": "HIGH",
                "student_2": "MID",
                "student_3": "LOW",
                "ANCHOR_A": "HIGH",
                "ANCHOR_B": "HIGH",
            },
            confidence_scores={
                "student_1": 0.9,
                "student_2": 0.7,
                "student_3": 0.5,
                "ANCHOR_A": 1.0,
                "ANCHOR_B": 0.95,
            },
        )

        # Act
        await publish_dual_assessment_events(
            rankings=rankings,
            grade_projections=grade_projections,
            publishing_data=publishing_data,
            event_publisher=mock_event_publisher,
            settings=test_settings,
            correlation_id=uuid4(),
        )

        # Assert
        resource_call = mock_event_publisher.publish_resource_consumption.call_args
        assert resource_call is not None

        resource_envelope = resource_call.kwargs["resource_event"]
        # Should be 3 students: 3 * 2 / 2 = 3 comparisons (anchors excluded)
        assert resource_envelope.data.quantity == 3

    @pytest.mark.asyncio
    async def test_resource_consumption_event_structure_and_fields(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_grade_projections: GradeProjectionSummary,
    ) -> None:
        """Test ResourceConsumptionV1 event creation, structure, and trace context."""
        publishing_data = DualEventPublishingData(
            bos_batch_id="bos_event_creation",
            cj_batch_id="cj_creation",
            assignment_id="assignment_creation",
            course_code=CourseCode.SV2.value,
            created_at=datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC),
            user_id="creation-user-456",
            org_id="creation-org-789",
        )
        rankings = [
            {"els_essay_id": "student_1", "bradley_terry_score": 0.8, "rank": 1},
            {"els_essay_id": "student_2", "bradley_terry_score": 0.6, "rank": 2},
        ]
        correlation_id = uuid4()

        await publish_dual_assessment_events(
            rankings=rankings,
            grade_projections=sample_grade_projections,
            publishing_data=publishing_data,
            event_publisher=mock_event_publisher,
            settings=test_settings,
            correlation_id=correlation_id,
        )

        resource_call = mock_event_publisher.publish_resource_consumption.call_args
        assert resource_call is not None
        resource_envelope = resource_call.kwargs["resource_event"]
        correlation_arg = resource_call.kwargs["correlation_id"]

        # Verify EventEnvelope structure
        assert isinstance(resource_envelope, EventEnvelope)
        assert resource_envelope.event_type == topic_name(
            ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED
        )
        assert resource_envelope.source_service == "cj_assessment_service"
        assert resource_envelope.correlation_id == correlation_id
        assert resource_envelope.metadata is not None  # Trace context injected

        # Verify ResourceConsumptionV1 data fields
        resource_data = resource_envelope.data
        assert isinstance(resource_data, ResourceConsumptionV1)
        assert resource_data.entity_id == "bos_event_creation"
        assert resource_data.entity_type == "batch"
        assert resource_data.user_id == "creation-user-456"
        assert resource_data.org_id == "creation-org-789"
        assert resource_data.resource_type == "cj_comparison"
        assert resource_data.quantity == 1  # 2 students = 1 comparison
        assert resource_data.service_name == "cj_assessment_service"
        assert resource_data.processing_id == "cj_creation"
        assert isinstance(resource_data.consumed_at, datetime)
        assert resource_data.consumed_at.tzinfo == UTC
        assert correlation_arg == correlation_id

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "org_id_input,expected_org_string",
        [("org-123", "org-123"), (None, None), ("", None), (12345, "12345")],
    )
    async def test_org_id_optional_handling_and_conversion(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_grade_projections: GradeProjectionSummary,
        org_id_input: Any,
        expected_org_string: str | None,
    ) -> None:
        """Test org_id optional behavior and proper None/string conversion."""
        publishing_data = DualEventPublishingData(
            bos_batch_id="bos_org_test",
            cj_batch_id="cj_org",
            assignment_id="assignment_org",
            course_code=CourseCode.ENG5.value,
            created_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
            user_id="org-test-user",
            org_id=str(org_id_input) if org_id_input not in (None, "") else None,
        )
        rankings = [{"els_essay_id": "student_1", "bradley_terry_score": 0.8, "rank": 1}]

        await publish_dual_assessment_events(
            rankings=rankings,
            grade_projections=sample_grade_projections,
            publishing_data=publishing_data,
            event_publisher=mock_event_publisher,
            settings=test_settings,
            correlation_id=uuid4(),
        )

        resource_call = mock_event_publisher.publish_resource_consumption.call_args
        assert resource_call is not None
        resource_envelope = resource_call.kwargs["resource_event"]
        assert resource_envelope.data.org_id == expected_org_string

    @pytest.mark.asyncio
    async def test_publishing_method_and_failure_handling(
        self,
        mock_event_publisher: AsyncMock,
        test_settings: Mock,
        sample_grade_projections: GradeProjectionSummary,
    ) -> None:
        """Test publish_resource_consumption call parameters and failure handling."""
        publishing_data = DualEventPublishingData(
            bos_batch_id="bos_method_test",
            cj_batch_id="cj_method",
            assignment_id="assignment_method",
            course_code=CourseCode.ENG5.value,
            created_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
            user_id="method-user-123",
            org_id="method-org-456",
        )
        rankings = [{"els_essay_id": "student_1", "bradley_terry_score": 0.8, "rank": 1}]
        correlation_id = uuid4()

        await publish_dual_assessment_events(
            rankings=rankings,
            grade_projections=sample_grade_projections,
            publishing_data=publishing_data,
            event_publisher=mock_event_publisher,
            settings=test_settings,
            correlation_id=correlation_id,
        )

        # Verify method was called correctly
        mock_event_publisher.publish_resource_consumption.assert_called_once()
        call_kwargs = mock_event_publisher.publish_resource_consumption.call_args.kwargs
        assert "resource_event" in call_kwargs and "correlation_id" in call_kwargs
        assert call_kwargs["correlation_id"] == correlation_id
        assert isinstance(call_kwargs["resource_event"], EventEnvelope)

        # Test failure handling - reset and make it fail
        mock_event_publisher.reset_mock()
        mock_event_publisher.publish_resource_consumption.side_effect = Exception("Failed")

        await publish_dual_assessment_events(
            rankings=rankings,
            grade_projections=sample_grade_projections,
            publishing_data=publishing_data,
            event_publisher=mock_event_publisher,
            settings=test_settings,
            correlation_id=uuid4(),
        )

        # Other events should still be published despite resource consumption failure
        mock_event_publisher.publish_assessment_completed.assert_called_once()
        mock_event_publisher.publish_assessment_result.assert_called_once()
        mock_event_publisher.publish_resource_consumption.assert_called_once()
