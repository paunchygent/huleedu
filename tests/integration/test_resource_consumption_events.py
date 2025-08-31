"""Integration tests for ResourceConsumptionV1 event publishing logic.

Tests the dual_event_publisher logic that creates ResourceConsumptionV1 events
during CJ Assessment completion, following established testing patterns.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.config_enums import LLMProviderType
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.cj_assessment_events import GradeProjectionSummary
from common_core.events.envelope import EventEnvelope
from common_core.events.resource_consumption_events import ResourceConsumptionV1
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.cj_core_logic.dual_event_publisher import (
    DualEventPublishingData,
    publish_dual_assessment_events,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.protocols import CJEventPublisherProtocol

logger = create_service_logger("test.resource_consumption_events")


# MockBatchUpload removed - using DualEventPublishingData directly


@pytest.fixture
def mock_settings():
    """Create a properly typed mock settings object."""
    settings = Mock(spec=Settings)
    settings.SERVICE_NAME = "cj_assessment_service"
    settings.CJ_ASSESSMENT_COMPLETED_TOPIC = "huleedu.cj_assessment.completed.v1"
    settings.DEFAULT_LLM_MODEL = "gpt-4"
    settings.DEFAULT_LLM_PROVIDER = LLMProviderType.OPENAI
    settings.DEFAULT_LLM_MODEL_VERSION = "20240101"
    settings.DEFAULT_LLM_TEMPERATURE = 0.0
    settings.ASSESSMENT_RESULT_TOPIC = "huleedu.assessment.results.v1"
    return settings


class TestResourceConsumptionEventPublishing:
    """Test ResourceConsumptionV1 event publishing logic."""

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        publisher = AsyncMock(spec=CJEventPublisherProtocol)
        publisher.publish_resource_consumption = AsyncMock()
        publisher.publish_assessment_completed = AsyncMock()
        return publisher

    @pytest.fixture
    def sample_rankings(self) -> list[dict[str, Any]]:
        return [
            {"els_essay_id": "essay_1", "bradley_terry_score": 0.75},
            {"els_essay_id": "essay_2", "bradley_terry_score": 0.60},
            {"els_essay_id": "essay_3", "bradley_terry_score": 0.45},
        ]

    @pytest.fixture
    def mock_grade_projections(self):
        return GradeProjectionSummary(
            projections_available=True,
            primary_grades={"essay_1": "A", "essay_2": "B", "essay_3": "B"},
            confidence_labels={"essay_1": "HIGH", "essay_2": "HIGH", "essay_3": "MID"},
            confidence_scores={"essay_1": 0.85, "essay_2": 0.80, "essay_3": 0.65}
        )

    @pytest.mark.integration
    async def test_resource_consumption_event_structure(
        self, mock_event_publisher: AsyncMock, sample_rankings: list, mock_grade_projections: Any, mock_settings: Mock
    ) -> None:
        """Test ResourceConsumptionV1 event structure and fields."""
        publishing_data = DualEventPublishingData(
            bos_batch_id="batch_123",
            cj_batch_id="cj_batch_123",
            assignment_id="test_assignment",
            course_code=CourseCode.ENG5.value,
            user_id="user_456",
            org_id="org_789",
            created_at=datetime.now(UTC)
        )
        correlation_id = uuid4()

        await publish_dual_assessment_events(
            rankings=sample_rankings,
            grade_projections=mock_grade_projections,
            publishing_data=publishing_data,
            event_publisher=mock_event_publisher,
            settings=mock_settings,
            correlation_id=correlation_id
        )

        mock_event_publisher.publish_resource_consumption.assert_called_once()
        call_args = mock_event_publisher.publish_resource_consumption.call_args
        resource_envelope = call_args[1]["resource_event"]
        
        # Validate event structure
        assert isinstance(resource_envelope, EventEnvelope)
        assert resource_envelope.event_type == topic_name(ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED)
        assert resource_envelope.correlation_id == correlation_id
        
        # Validate event data
        resource_data = resource_envelope.data
        assert isinstance(resource_data, ResourceConsumptionV1)
        assert resource_data.entity_id == "batch_123"
        assert resource_data.entity_type == "batch"
        assert resource_data.resource_type == "cj_comparison"
        assert resource_data.quantity == 3  # 3*(3-1)/2 = 3 comparisons
        assert resource_data.service_name == "cj_assessment_service"

    @pytest.mark.integration
    async def test_identity_threading_preservation(
        self, mock_event_publisher: AsyncMock, sample_rankings: list, mock_grade_projections: Any, mock_settings: Mock
    ) -> None:
        """Test user_id/org_id preservation in ResourceConsumptionV1."""
        publishing_data = DualEventPublishingData(
            bos_batch_id="identity_test",
            cj_batch_id="cj_identity_test",
            assignment_id="test_assignment",
            course_code=CourseCode.ENG5.value,
            user_id="teacher_123",
            org_id="school_456",
            created_at=datetime.now(UTC)
        )
        correlation_id = uuid4()

        await publish_dual_assessment_events(
            rankings=sample_rankings,
            grade_projections=mock_grade_projections,
            publishing_data=publishing_data,
            event_publisher=mock_event_publisher,
            settings=mock_settings,
            correlation_id=correlation_id
        )

        call_args = mock_event_publisher.publish_resource_consumption.call_args
        resource_envelope = call_args[1]["resource_event"]
        resource_data = resource_envelope.data
        
        # Validate identity threading
        assert resource_data.user_id == "teacher_123"
        assert resource_data.org_id == "school_456"

    @pytest.mark.integration
    async def test_comparison_calculation_accuracy(
        self, mock_event_publisher: AsyncMock, mock_grade_projections: Any, mock_settings: Mock
    ) -> None:
        """Test comparison quantity calculation for different essay counts."""
        test_cases = [
            (2, 1),    # 2 essays = 1 comparison
            (3, 3),    # 3 essays = 3 comparisons
            (4, 6),    # 4 essays = 6 comparisons
            (5, 10),   # 5 essays = 10 comparisons
        ]
        
        for essay_count, expected_comparisons in test_cases:
            rankings = [{"els_essay_id": f"essay_{i}", "bradley_terry_score": 0.5} 
                       for i in range(essay_count)]
            
            publishing_data = DualEventPublishingData(
                bos_batch_id=f"batch_{essay_count}",
                cj_batch_id=f"cj_batch_{essay_count}",
                assignment_id="test_assignment",
                course_code=CourseCode.ENG5.value,
                user_id="user_test",
                org_id="org_test",
                created_at=datetime.now(UTC)
            )
            
            await publish_dual_assessment_events(
                rankings=rankings,
                grade_projections=mock_grade_projections,
                publishing_data=publishing_data,
                event_publisher=mock_event_publisher,
                settings=mock_settings,
                correlation_id=uuid4()
            )
            
            call_args = mock_event_publisher.publish_resource_consumption.call_args
            resource_data = call_args[1]["resource_event"].data
            assert resource_data.quantity == expected_comparisons

    @pytest.mark.integration 
    async def test_missing_user_id_validation(
        self, mock_event_publisher: AsyncMock, sample_rankings: list, mock_grade_projections: Any, mock_settings: Mock
    ) -> None:
        """Test graceful handling when user_id is missing - should skip resource consumption but continue with other events."""
        publishing_data = DualEventPublishingData(
            bos_batch_id="batch_no_user",
            cj_batch_id="cj_batch_no_user",
            assignment_id="test_assignment",
            course_code=CourseCode.ENG5.value,
            user_id="required_user_123",  # user_id is required, so providing a test value
            org_id="org_test",
            created_at=datetime.now(UTC)
        )
        
        # Should complete without raising exception (resilient behavior)
        await publish_dual_assessment_events(
            rankings=sample_rankings,
            grade_projections=mock_grade_projections,
            publishing_data=publishing_data,
            event_publisher=mock_event_publisher,
            settings=mock_settings,
            correlation_id=uuid4()
        )
        
        # All events should be published successfully since user_id is now required
        mock_event_publisher.publish_assessment_completed.assert_called_once()
        mock_event_publisher.publish_assessment_result.assert_called_once()
        mock_event_publisher.publish_resource_consumption.assert_called_once()

    @pytest.mark.integration
    async def test_missing_org_id_fallback_behavior(
        self, mock_event_publisher: AsyncMock, sample_rankings: list, mock_grade_projections: Any, mock_settings: Mock
    ) -> None:
        """Test org-first, user-fallback behavior - resource consumption should work with user_id only."""
        publishing_data = DualEventPublishingData(
            bos_batch_id="batch_user_fallback",
            cj_batch_id="cj_batch_user_fallback",
            assignment_id="test_assignment",
            course_code=CourseCode.ENG5.value,
            user_id="individual_user_123",
            org_id=None,
            created_at=datetime.now(UTC)
        )
        correlation_id = uuid4()
        
        await publish_dual_assessment_events(
            rankings=sample_rankings,
            grade_projections=mock_grade_projections,
            publishing_data=publishing_data,
            event_publisher=mock_event_publisher,
            settings=mock_settings,
            correlation_id=correlation_id
        )
        
        # All events should be published successfully
        mock_event_publisher.publish_assessment_completed.assert_called_once()
        mock_event_publisher.publish_assessment_result.assert_called_once()
        mock_event_publisher.publish_resource_consumption.assert_called_once()
        
        # Verify resource consumption event has user_id but no org_id (fallback behavior)
        call_args = mock_event_publisher.publish_resource_consumption.call_args
        resource_envelope = call_args[1]["resource_event"]
        resource_data = resource_envelope.data
        
        assert resource_data.user_id == "individual_user_123"
        assert resource_data.org_id is None  # Fallback to individual user

    @pytest.mark.integration
    async def test_swedish_character_preservation(
        self, mock_event_publisher: AsyncMock, sample_rankings: list, mock_grade_projections: Any, mock_settings: Mock
    ) -> None:
        """Test Swedish character preservation in identity fields."""
        publishing_data = DualEventPublishingData(
            bos_batch_id="batch_åäö",
            cj_batch_id="cj_batch_åäö",
            assignment_id="test_assignment",
            course_code=CourseCode.ENG5.value,
            user_id="lärare_åsa",
            org_id="skola_västerås",
            created_at=datetime.now(UTC)
        )
        
        await publish_dual_assessment_events(
            rankings=sample_rankings,
            grade_projections=mock_grade_projections,
            publishing_data=publishing_data,
            event_publisher=mock_event_publisher,
            settings=mock_settings,
            correlation_id=uuid4()
        )
        
        call_args = mock_event_publisher.publish_resource_consumption.call_args
        resource_data = call_args[1]["resource_event"].data
        
        # Validate Swedish characters preserved
        assert resource_data.user_id == "lärare_åsa"
        assert resource_data.org_id == "skola_västerås"
        assert resource_data.entity_id == "batch_åäö"

    @pytest.mark.integration
    async def test_event_serialization_compatibility(
        self, mock_event_publisher: AsyncMock, sample_rankings: list, mock_grade_projections: Any, mock_settings: Mock
    ) -> None:
        """Test event can be properly serialized for Kafka."""
        publishing_data = DualEventPublishingData(
            bos_batch_id="serialization_test",
            cj_batch_id="cj_serialization_test",
            assignment_id="test_assignment",
            course_code=CourseCode.ENG5.value,
            user_id="user_123",
            org_id="org_456",
            created_at=datetime.now(UTC)
        )
        
        await publish_dual_assessment_events(
            rankings=sample_rankings,
            grade_projections=mock_grade_projections,
            publishing_data=publishing_data,
            event_publisher=mock_event_publisher,
            settings=mock_settings,
            correlation_id=uuid4()
        )
        
        call_args = mock_event_publisher.publish_resource_consumption.call_args
        resource_envelope = call_args[1]["resource_event"]
        
        # Test serialization/deserialization
        serialized = resource_envelope.model_dump(mode="json")
        json_str = json.dumps(serialized)
        deserialized = json.loads(json_str)
        
        # Validate key fields survive serialization
        assert deserialized["event_type"] == "huleedu.resource.consumption.v1"
        assert deserialized["data"]["resource_type"] == "cj_comparison"
        assert deserialized["data"]["user_id"] == "user_123"
        assert deserialized["data"]["org_id"] == "org_456"