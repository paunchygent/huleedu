"""
Shared utilities, fixtures, and imports for BOS orchestration test suite.

This module provides common test fixtures and setup used across multiple
BOS orchestration test files to avoid duplication and maintain consistency.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

# Models from common_core
from common_core.metadata_models import (
    EssayProcessingInputRefV1,
)
from common_core.pipeline_models import (
    PhaseName,
)

# BOS specific models
from services.batch_orchestrator_service.api_models import (
    BatchRegistrationRequestV1,
)
from services.batch_orchestrator_service.config import (
    settings as bos_settings,
)

# BOS implementations and protocols
from services.batch_orchestrator_service.implementations.batch_processing_service_impl import (
    BatchProcessingServiceImpl,
)
from services.batch_orchestrator_service.implementations.cj_assessment_initiator_impl import (
    DefaultCJAssessmentInitiator,
)
from services.batch_orchestrator_service.implementations.pipeline_phase_coordinator_impl import (
    DefaultPipelinePhaseCoordinator,
)
from services.batch_orchestrator_service.protocols import (
    BatchEventPublisherProtocol,
    BatchRepositoryProtocol,
    CJAssessmentInitiatorProtocol,
    PipelinePhaseInitiatorProtocol,
)

# Pytest asyncio marker
pytestmark = pytest.mark.asyncio


@pytest.fixture
def sample_correlation_id() -> uuid.UUID:
    """Provides a sample correlation ID."""
    return uuid.uuid4()


@pytest.fixture
def sample_batch_id(sample_correlation_id: uuid.UUID) -> str:
    """Provides a sample batch ID, derived from correlation_id for consistency if needed."""
    # Or simply return str(uuid.uuid4()) if independent ID is preferred
    return str(sample_correlation_id)


@pytest.fixture
def mock_batch_repo() -> AsyncMock:
    """Mocks the BatchRepositoryProtocol."""
    mock = AsyncMock(spec=BatchRepositoryProtocol)
    mock.get_batch_context.return_value = None
    mock.get_processing_pipeline_state.return_value = None
    mock.store_batch_context = AsyncMock(return_value=True)
    mock.save_processing_pipeline_state = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Mocks the BatchEventPublisherProtocol."""
    return AsyncMock(spec=BatchEventPublisherProtocol)


@pytest.fixture
def mock_cj_initiator() -> AsyncMock:
    """Mocks the CJAssessmentInitiatorProtocol."""
    mock = AsyncMock(spec=CJAssessmentInitiatorProtocol)
    mock.initiate_phase = AsyncMock()
    return mock


@pytest.fixture
def batch_processing_service(
    mock_batch_repo: AsyncMock,
    mock_event_publisher: AsyncMock,
) -> BatchProcessingServiceImpl:
    """Provides an instance of BatchProcessingServiceImpl with mocked dependencies."""
    return BatchProcessingServiceImpl(
        batch_repo=mock_batch_repo,
        event_publisher=mock_event_publisher,
        settings=bos_settings,
    )


@pytest.fixture
def pipeline_phase_coordinator(
    mock_batch_repo: AsyncMock,
    mock_cj_initiator: AsyncMock,
) -> DefaultPipelinePhaseCoordinator:
    """Provides an instance of DefaultPipelinePhaseCoordinator with mocked dependencies."""
    # Create mock phase_initiators_map for dynamic phase coordination
    mock_phase_initiators_map = {
        PhaseName.SPELLCHECK: AsyncMock(spec=PipelinePhaseInitiatorProtocol),
        PhaseName.CJ_ASSESSMENT: mock_cj_initiator,
        PhaseName.AI_FEEDBACK: AsyncMock(spec=PipelinePhaseInitiatorProtocol),
        PhaseName.NLP: AsyncMock(spec=PipelinePhaseInitiatorProtocol),
    }
    return DefaultPipelinePhaseCoordinator(
        batch_repo=mock_batch_repo, phase_initiators_map=mock_phase_initiators_map
    )


@pytest.fixture
def cj_assessment_initiator(
    mock_event_publisher: AsyncMock,
    mock_batch_repo: AsyncMock,
) -> DefaultCJAssessmentInitiator:
    """Provides an instance of DefaultCJAssessmentInitiator with mocked dependencies."""
    return DefaultCJAssessmentInitiator(
        event_publisher=mock_event_publisher, batch_repo=mock_batch_repo
    )


@pytest.fixture
def sample_batch_registration_request_cj_enabled() -> BatchRegistrationRequestV1:
    """Provides a sample BatchRegistrationRequestV1 with CJ assessment enabled."""
    return BatchRegistrationRequestV1(
        expected_essay_count=2,
        course_code="ENG101",
        class_designation="Class A",
        teacher_name="Dr. Smith",
        essay_instructions="Write an essay on the impact of AI.",
        enable_cj_assessment=True,
        cj_default_llm_model="gpt-4o-mini",
        cj_default_temperature=0.5,
    )


@pytest.fixture
def sample_batch_registration_request_cj_disabled() -> BatchRegistrationRequestV1:
    """Provides a sample BatchRegistrationRequestV1 with CJ assessment disabled."""
    return BatchRegistrationRequestV1(
        expected_essay_count=2,
        course_code="SCI202",
        class_designation="Class B",
        teacher_name="Mr. Jones",
        essay_instructions="Submit your lab report on photosynthesis.",
        enable_cj_assessment=False,
    )


@pytest.fixture
def sample_essay_refs() -> list[EssayProcessingInputRefV1]:
    """Provides a list of sample EssayProcessingInputRefV1 objects."""
    return [
        EssayProcessingInputRefV1(essay_id=str(uuid.uuid4()), text_storage_id=str(uuid.uuid4())),
        EssayProcessingInputRefV1(essay_id=str(uuid.uuid4()), text_storage_id=str(uuid.uuid4())),
    ]
