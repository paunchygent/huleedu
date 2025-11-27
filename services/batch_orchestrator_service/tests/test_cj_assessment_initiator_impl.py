"""Unit tests for DefaultCJAssessmentInitiator implementation.

Verifies that CJ assessment commands are constructed correctly and that
assignment_id from batch context is propagated into the BOS→ELS command.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from common_core.batch_service_models import (
    BatchServiceCJAssessmentInitiateCommandDataV1,
)
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EssayProcessingInputRefV1
from common_core.pipeline_models import PhaseName

from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.implementations.cj_assessment_initiator_impl import (
    DefaultCJAssessmentInitiator,
)
from services.batch_orchestrator_service.protocols import (
    BatchEventPublisherProtocol,
    BatchRepositoryProtocol,
)


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Mock event publisher for testing."""
    return AsyncMock(spec=BatchEventPublisherProtocol)


@pytest.fixture
def mock_batch_repository() -> AsyncMock:
    """Mock batch repository protocol for testing."""
    return AsyncMock(spec=BatchRepositoryProtocol)


@pytest.fixture
def cj_initiator(
    mock_event_publisher: AsyncMock,
    mock_batch_repository: AsyncMock,
) -> DefaultCJAssessmentInitiator:
    """Create DefaultCJAssessmentInitiator with mocked dependencies."""
    return DefaultCJAssessmentInitiator(
        event_publisher=mock_event_publisher,
        batch_repo=mock_batch_repository,
    )


@pytest.fixture
def sample_batch_context() -> BatchRegistrationRequestV1:
    """Sample batch registration context including assignment_id."""
    return BatchRegistrationRequestV1(
        expected_essay_count=2,
        essay_ids=["essay-1", "essay-2"],
        course_code=CourseCode.ENG5,
        student_prompt_ref=None,
        user_id="test-teacher",
        org_id=None,
        class_id=None,
        cj_default_llm_model=None,
        cj_default_temperature=None,
        assignment_id="assignment-123",
    )


@pytest.fixture
def sample_essays() -> list[EssayProcessingInputRefV1]:
    """Sample essays to process for CJ assessment."""
    return [
        EssayProcessingInputRefV1(essay_id="essay-1", text_storage_id="storage-1"),
        EssayProcessingInputRefV1(essay_id="essay-2", text_storage_id="storage-2"),
    ]


@pytest.fixture
def sample_correlation_id() -> UUID:
    """Sample correlation ID."""
    return uuid4()


class TestDefaultCJAssessmentInitiator:
    """Test suite for DefaultCJAssessmentInitiator."""

    @pytest.mark.asyncio
    async def test_initiate_phase_includes_assignment_id(
        self,
        cj_initiator: DefaultCJAssessmentInitiator,
        mock_event_publisher: AsyncMock,
        sample_batch_context: BatchRegistrationRequestV1,
        sample_essays: list[EssayProcessingInputRefV1],
        sample_correlation_id: UUID,
    ) -> None:
        """CJ command should include assignment_id from batch context."""
        batch_id = "batch-cj-123"

        await cj_initiator.initiate_phase(
            batch_id=batch_id,
            phase_to_initiate=PhaseName.CJ_ASSESSMENT,
            correlation_id=sample_correlation_id,
            essays_for_processing=sample_essays,
            batch_context=sample_batch_context,
        )

        mock_event_publisher.publish_batch_event.assert_called_once()
        envelope: EventEnvelope[BatchServiceCJAssessmentInitiateCommandDataV1] = (
            mock_event_publisher.publish_batch_event.call_args.args[0]
        )

        assert envelope.event_type == topic_name(
            ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND,
        )
        assert envelope.correlation_id == sample_correlation_id
        assert isinstance(envelope.data, BatchServiceCJAssessmentInitiateCommandDataV1)

        command = envelope.data
        assert command.entity_id == batch_id
        assert command.assignment_id == "assignment-123"
