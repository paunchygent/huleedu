"""CJ Assessment → Entitlements identity threading integration tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent
from common_core.events.envelope import EventEnvelope
from common_core.events.resource_consumption_events import ResourceConsumptionV1
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.cj_core_logic.dual_event_publisher import (
    publish_dual_assessment_events,
)
from services.cj_assessment_service.protocols import CJEventPublisherProtocol
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager

logger = create_service_logger("test.cj_entitlements_identity")


class MockBatchUpload:
    """Mock CJ batch upload with identity fields."""

    def __init__(self, bos_batch_id: str, user_id: str | None = None, org_id: str | None = None):
        self.bos_batch_id = bos_batch_id
        self.id = f"cj_{bos_batch_id}"
        self.user_id = user_id
        self.org_id = org_id
        self.course_code = CourseCode.ENG5
        self.assignment_id = "test_assignment"
        self.created_at = datetime.now(UTC)


class MockSettings:
    """Mock CJ service settings."""
    SERVICE_NAME = "cj_assessment_service"
    CJ_ASSESSMENT_COMPLETED_TOPIC = "huleedu.cj_assessment.completed.v1"
    ASSESSMENT_RESULT_TOPIC = "huleedu.assessment.result.published.v1"
    DEFAULT_LLM_MODEL = "gpt-4"
    DEFAULT_LLM_PROVIDER = type('Provider', (), {'value': 'openai'})()
    DEFAULT_LLM_TEMPERATURE = 0.0


class TestCJEntitlementsIdentityFlow:
    """Test identity threading from CJ Assessment to Entitlements Service."""

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Mock CJ event publisher."""
        publisher = AsyncMock(spec=CJEventPublisherProtocol)
        publisher.publish_resource_consumption = AsyncMock()
        publisher.publish_assessment_completed = AsyncMock()
        publisher.publish_assessment_result = AsyncMock()
        return publisher

    @pytest.fixture
    def sample_rankings(self) -> list[dict[str, Any]]:
        """Sample essay rankings."""
        return [
            {"els_essay_id": "essay_1", "bradley_terry_score": 0.75},
            {"els_essay_id": "essay_2", "bradley_terry_score": 0.60},
            {"els_essay_id": "essay_3", "bradley_terry_score": 0.45},
            {"els_essay_id": "essay_4", "bradley_terry_score": 0.30},
        ]

    @pytest.fixture
    def mock_grade_projections(self) -> Any:
        """Mock grade projections."""
        from common_core.events.cj_assessment_events import GradeProjectionSummary
        return GradeProjectionSummary(
            projections_available=True,
            primary_grades={"essay_1": "A", "essay_2": "B", "essay_3": "B", "essay_4": "C"},
            confidence_labels={"essay_1": "HIGH", "essay_2": "HIGH", "essay_3": "MID", "essay_4": "LOW"},
            confidence_scores={"essay_1": 0.85, "essay_2": 0.80, "essay_3": 0.65, "essay_4": 0.45}
        )

    @pytest.mark.integration
    async def test_cj_identity_propagation_to_entitlements(
        self, mock_event_publisher: AsyncMock, sample_rankings: list, mock_grade_projections: Any
    ) -> None:
        """Test user_id/org_id propagation CJ → ResourceConsumptionV1."""
        # Arrange
        batch_upload = MockBatchUpload(
            bos_batch_id="batch_identity_test", user_id="teacher_123", org_id="school_456"
        )
        correlation_id = uuid4()

        # Act
        await publish_dual_assessment_events(
            rankings=sample_rankings,
            grade_projections=mock_grade_projections,
            batch_upload=batch_upload,
            event_publisher=mock_event_publisher,
            settings=MockSettings(),  # type: ignore[arg-type]
            correlation_id=correlation_id,
        )

        # Assert - ResourceConsumptionV1 called with correct identity
        mock_event_publisher.publish_resource_consumption.assert_called_once()
        resource_call = mock_event_publisher.publish_resource_consumption.call_args
        resource_envelope = resource_call.kwargs["resource_event"]
        
        assert isinstance(resource_envelope.data, ResourceConsumptionV1)
        assert resource_envelope.data.user_id == "teacher_123"
        assert resource_envelope.data.org_id == "school_456"
        assert resource_envelope.data.entity_id == "batch_identity_test"
        assert resource_envelope.data.entity_type == "batch"

    @pytest.mark.integration
    async def test_batch_id_mapping_entity_type_batch(
        self, mock_event_publisher: AsyncMock, sample_rankings: list, mock_grade_projections: Any
    ) -> None:
        """Test batch_id mapping when entity_type=batch."""
        # Arrange
        batch_upload = MockBatchUpload(
            bos_batch_id="bos_batch_mapping", user_id="user_mapping", org_id="org_mapping"
        )

        # Act
        await publish_dual_assessment_events(
            rankings=sample_rankings,
            grade_projections=mock_grade_projections,
            batch_upload=batch_upload,
            event_publisher=mock_event_publisher,
            settings=MockSettings(),  # type: ignore[arg-type]
            correlation_id=uuid4(),
        )

        # Assert
        resource_envelope = mock_event_publisher.publish_resource_consumption.call_args.kwargs[
            "resource_event"
        ]
        assert resource_envelope.data.entity_id == "bos_batch_mapping"
        assert resource_envelope.data.entity_type == "batch"

    @pytest.mark.integration
    async def test_correlation_id_preservation(
        self, mock_event_publisher: AsyncMock, sample_rankings: list, mock_grade_projections: Any
    ) -> None:
        """Test correlation_id preservation across events."""
        # Arrange
        batch_upload = MockBatchUpload(
            bos_batch_id="correlation_test", user_id="corr_user", org_id="corr_org"
        )
        test_correlation_id = uuid4()

        # Act
        await publish_dual_assessment_events(
            rankings=sample_rankings,
            grade_projections=mock_grade_projections,
            batch_upload=batch_upload,
            event_publisher=mock_event_publisher,
            settings=MockSettings(),  # type: ignore[arg-type]
            correlation_id=test_correlation_id,
        )

        # Assert - Both events preserve correlation_id
        resource_envelope = mock_event_publisher.publish_resource_consumption.call_args.kwargs[
            "resource_event"
        ]
        assert resource_envelope.correlation_id == test_correlation_id

        completion_envelope = mock_event_publisher.publish_assessment_completed.call_args.kwargs[
            "completion_data"
        ]
        assert completion_envelope.correlation_id == test_correlation_id

    @pytest.mark.integration
    async def test_quantity_mapping_processed_essays_to_consumption(
        self, mock_event_publisher: AsyncMock, mock_grade_projections: Any
    ) -> None:
        """Test quantity mapping from processed essays to credit consumption."""
        # Arrange - 6 essays = 15 comparisons: 6*(6-1)/2 = 15
        rankings = [
            {"els_essay_id": f"essay_{i}", "bradley_terry_score": 0.5} for i in range(1, 7)
        ]
        batch_upload = MockBatchUpload(
            bos_batch_id="quantity_test", user_id="quantity_user", org_id="quantity_org"
        )

        # Act
        await publish_dual_assessment_events(
            rankings=rankings,
            grade_projections=mock_grade_projections,
            batch_upload=batch_upload,
            event_publisher=mock_event_publisher,
            settings=MockSettings(),  # type: ignore[arg-type]
            correlation_id=uuid4(),
        )

        # Assert
        resource_envelope = mock_event_publisher.publish_resource_consumption.call_args.kwargs[
            "resource_event"
        ]
        assert resource_envelope.data.quantity == 15  # 6*5/2 comparisons
        assert resource_envelope.data.resource_type == "cj_comparison"

    @pytest.mark.integration
    @pytest.mark.parametrize(
        "user_id,org_id,expected_user,expected_org",
        [
            ("lärare-åäö", "skola-växjö", "lärare-åäö", "skola-växjö"),
            ("teacher-Ås", "Västerås-gymnasium", "teacher-Ås", "Västerås-gymnasium"),
        ],
    )
    async def test_swedish_characters_identity_preservation(
        self,
        user_id: str,
        org_id: str,
        expected_user: str,
        expected_org: str,
        mock_event_publisher: AsyncMock,
        sample_rankings: list,
        mock_grade_projections: Any,
    ) -> None:
        """Test Swedish character preservation in identity fields."""
        # Arrange
        batch_upload = MockBatchUpload(
            bos_batch_id="swedish_test", user_id=user_id, org_id=org_id
        )

        # Act
        await publish_dual_assessment_events(
            rankings=sample_rankings,
            grade_projections=mock_grade_projections,
            batch_upload=batch_upload,
            event_publisher=mock_event_publisher,
            settings=MockSettings(),  # type: ignore[arg-type]
            correlation_id=uuid4(),
        )

        # Assert
        resource_envelope = mock_event_publisher.publish_resource_consumption.call_args.kwargs[
            "resource_event"
        ]
        assert resource_envelope.data.user_id == expected_user
        assert resource_envelope.data.org_id == expected_org


    @pytest.mark.integration
    async def test_missing_user_id_graceful_handling(
        self, mock_event_publisher: AsyncMock, sample_rankings: list, mock_grade_projections: Any
    ) -> None:
        """Test missing user_id is handled gracefully (logged but not raised)."""
        # Arrange
        batch_upload = MockBatchUpload(
            bos_batch_id="missing_user_test", user_id=None, org_id="test_org"
        )

        # Act - Should not raise exception, failure is logged
        await publish_dual_assessment_events(
            rankings=sample_rankings,
            grade_projections=mock_grade_projections,
            batch_upload=batch_upload,
            event_publisher=mock_event_publisher,
            settings=MockSettings(),  # type: ignore[arg-type]
            correlation_id=uuid4(),
        )
        
        # Assert - Main events still published, resource consumption not called
        mock_event_publisher.publish_assessment_completed.assert_called_once()
        mock_event_publisher.publish_assessment_result.assert_called_once()
        mock_event_publisher.publish_resource_consumption.assert_not_called()

    @pytest.mark.integration
    async def test_individual_user_org_id_none(
        self, mock_event_publisher: AsyncMock, sample_rankings: list, mock_grade_projections: Any
    ) -> None:
        """Test org_id=None for individual users."""
        # Arrange
        batch_upload = MockBatchUpload(
            bos_batch_id="individual_test", user_id="individual_teacher", org_id=None
        )

        # Act
        await publish_dual_assessment_events(
            rankings=sample_rankings,
            grade_projections=mock_grade_projections,
            batch_upload=batch_upload,
            event_publisher=mock_event_publisher,
            settings=MockSettings(),  # type: ignore[arg-type]
            correlation_id=uuid4(),
        )

        # Assert
        resource_envelope = mock_event_publisher.publish_resource_consumption.call_args.kwargs[
            "resource_event"
        ]
        assert resource_envelope.data.user_id == "individual_teacher"
        assert resource_envelope.data.org_id is None

    @pytest.mark.integration
    async def test_event_publishing_failure_handling(
        self, sample_rankings: list, mock_grade_projections: Any
    ) -> None:
        """Test resource consumption publishing failure is handled gracefully."""
        # Arrange
        batch_upload = MockBatchUpload(
            bos_batch_id="failure_test", user_id="failure_user", org_id="failure_org"
        )
        
        failing_publisher = AsyncMock(spec=CJEventPublisherProtocol)
        failing_publisher.publish_assessment_completed = AsyncMock()
        failing_publisher.publish_resource_consumption = AsyncMock(
            side_effect=Exception("Publishing failed")
        )

        # Act - Should not raise exception, just log warning
        await publish_dual_assessment_events(
            rankings=sample_rankings,
            grade_projections=mock_grade_projections,
            batch_upload=batch_upload,
            event_publisher=failing_publisher,
            settings=MockSettings(),  # type: ignore[arg-type]
            correlation_id=uuid4(),
        )

        # Assert - Main event still published, error logged but not raised
        failing_publisher.publish_assessment_completed.assert_called_once()
        failing_publisher.publish_resource_consumption.assert_called_once()


    @pytest.mark.integration
    async def test_batch_size_to_quantity_mapping_edge_cases(
        self, mock_event_publisher: AsyncMock, mock_grade_projections: Any
    ) -> None:
        """Test batch size to quantity mapping for edge cases."""
        # Arrange - Single essay (0 comparisons)
        rankings = [{"els_essay_id": "single_essay", "bradley_terry_score": 0.5}]
        batch_upload = MockBatchUpload(
            bos_batch_id="single_essay_test", user_id="edge_user", org_id="edge_org"
        )

        # Act
        await publish_dual_assessment_events(
            rankings=rankings,
            grade_projections=mock_grade_projections,
            batch_upload=batch_upload,
            event_publisher=mock_event_publisher,
            settings=MockSettings(),  # type: ignore[arg-type]
            correlation_id=uuid4(),
        )

        # Assert
        resource_envelope = mock_event_publisher.publish_resource_consumption.call_args.kwargs[
            "resource_event"
        ]
        assert resource_envelope.data.quantity == 0  # Single essay = 0 comparisons


    @pytest.mark.integration
    async def test_credit_attribution_accuracy_with_service_metadata(
        self, mock_event_publisher: AsyncMock, sample_rankings: list, mock_grade_projections: Any
    ) -> None:
        """Test credit attribution accuracy with complete service metadata."""
        # Arrange
        batch_upload = MockBatchUpload(
            bos_batch_id="attribution_test", user_id="attribution_user", org_id="attribution_org"
        )
        correlation_id = uuid4()

        # Act
        await publish_dual_assessment_events(
            rankings=sample_rankings,
            grade_projections=mock_grade_projections,
            batch_upload=batch_upload,
            event_publisher=mock_event_publisher,
            settings=MockSettings(),  # type: ignore[arg-type]
            correlation_id=correlation_id,
        )

        # Assert - Complete ResourceConsumptionV1 structure
        resource_envelope = mock_event_publisher.publish_resource_consumption.call_args.kwargs[
            "resource_event"
        ]
        resource_data = resource_envelope.data
        
        assert resource_data.service_name == "cj_assessment_service"
        assert resource_data.processing_id == f"cj_attribution_test"
        assert resource_data.consumed_at is not None
        assert resource_data.entity_id == "attribution_test"
        assert resource_data.user_id == "attribution_user"
        assert resource_data.org_id == "attribution_org"
        assert resource_envelope.correlation_id == correlation_id
        assert resource_envelope.source_service == "cj_assessment_service"