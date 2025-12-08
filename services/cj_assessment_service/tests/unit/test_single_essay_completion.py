"""Unit tests for single-essay completion finalizer.

Verifies that batches with fewer than 2 student essays are finalized
without comparisons, with proper status updates and event publishing.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core.events.cj_assessment_events import GradeProjectionSummary
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.batch_finalizer import (
    BatchFinalizer,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_db import (
    CJBatchUpload,
    ProcessedEssay,
)
from services.cj_assessment_service.protocols import (
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    CJEssayRepositoryProtocol,
    CJEventPublisherProtocol,
    ContentClientProtocol,
)
from services.cj_assessment_service.tests.unit.test_mocks import MockSessionProvider


@pytest.fixture
def mock_session_provider() -> MockSessionProvider:
    """Provide mock session provider for tests."""
    return MockSessionProvider()


@pytest.fixture
def mock_essay_repo() -> AsyncMock:
    """Provide mock essay repository."""
    return AsyncMock(spec=CJEssayRepositoryProtocol)


@pytest.fixture
def mock_batch_repo() -> AsyncMock:
    """Provide mock batch repository."""
    return AsyncMock(spec=CJBatchRepositoryProtocol)


@pytest.mark.asyncio
async def test_finalize_single_essay_publishes_and_updates(
    monkeypatch: Any,
    mock_session_provider: MockSessionProvider,
    mock_essay_repo: AsyncMock,
    mock_batch_repo: AsyncMock,
) -> None:
    # Arrange
    correlation_id = uuid4()

    batch = CJBatchUpload()
    batch.id = 101
    batch.bos_batch_id = "bos-xyz"
    batch.event_correlation_id = str(correlation_id)
    batch.language = "sv"
    batch.course_code = "SV2"
    batch.expected_essay_count = 1
    batch.status = CJBatchStatusEnum.PENDING
    batch.created_at = datetime.now(UTC)
    batch.user_id = "test-user"
    batch.org_id = "test-org"
    batch.assignment_id = None
    batch.processing_metadata = {"student_prompt_text": "Assess writing"}

    essay = ProcessedEssay()
    essay.els_essay_id = "student_1"
    essay.cj_batch_id = batch.id
    essay.assessment_input_text = "Lorem ipsum"
    essay.is_anchor = False
    essay.current_bt_score = None

    # Configure mock essay repository
    mock_essay_repo.get_essays_for_cj_batch.return_value = [essay]

    # Mock the session returned by MockSessionProvider to return the batch on get()
    original_session_method = mock_session_provider.session

    @asynccontextmanager
    async def patched_session() -> AsyncIterator[AsyncSession]:
        async with original_session_method() as session:
            # Replace get with an AsyncMock that returns the batch
            get_mock = AsyncMock(return_value=batch)
            monkeypatch.setattr(session, "get", get_mock)
            yield session

    monkeypatch.setattr(mock_session_provider, "session", patched_session)

    event_publisher = AsyncMock(spec=CJEventPublisherProtocol)
    content_client = AsyncMock(spec=ContentClientProtocol)

    # Settings required by publisher
    settings = Mock(spec=Settings)
    settings.SERVICE_NAME = "cj_assessment_service"
    settings.CJ_ASSESSMENT_COMPLETED_TOPIC = "processing.cj.assessment.completed.v1"
    settings.ASSESSMENT_RESULT_TOPIC = "processing.assessment.result.v1"
    settings.DEFAULT_LLM_MODEL = "test-model"
    settings.DEFAULT_LLM_PROVIDER = Mock(value="test-provider")
    settings.DEFAULT_LLM_TEMPERATURE = 0.0

    # Mock ranking and projections to avoid heavy dependencies
    from services.cj_assessment_service.cj_core_logic import batch_finalizer as bf

    class _FakeSR:
        async def get_essay_rankings(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            return [
                {
                    "rank": 1,
                    "els_essay_id": "student_1",
                    "bradley_terry_score": 0.0,
                    "bradley_terry_se": None,
                    "comparison_count": 0,
                    "is_anchor": False,
                }
            ]

    class _FakeGP:
        class GradeProjector:
            async def calculate_projections(
                self, *_args: Any, **_kwargs: Any
            ) -> GradeProjectionSummary:
                return GradeProjectionSummary(
                    projections_available=False,
                    primary_grades={},
                    confidence_labels={},
                    confidence_scores={},
                )

    monkeypatch.setattr(bf, "scoring_ranking", _FakeSR())

    log_extra = {"correlation_id": str(correlation_id)}

    # Act
    from services.cj_assessment_service.cj_core_logic.grade_projector import (
        GradeProjector,
    )

    grade_projector = AsyncMock(spec=GradeProjector)
    grade_projector.calculate_projections.return_value = GradeProjectionSummary(
        projections_available=False,
        primary_grades={},
        confidence_labels={},
        confidence_scores={},
    )
    finalizer = BatchFinalizer(
        session_provider=mock_session_provider,
        batch_repository=mock_batch_repo,
        comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
        essay_repository=mock_essay_repo,
        event_publisher=event_publisher,
        content_client=content_client,
        settings=settings,
        grade_projector=grade_projector,
    )
    await finalizer.finalize_single_essay(
        batch_id=batch.id,
        correlation_id=correlation_id,
        log_extra=log_extra,
    )

    # Assert: status updated, minimal score set, events published
    mock_batch_repo.update_cj_batch_status.assert_called()
    status_call_args = mock_batch_repo.update_cj_batch_status.call_args
    assert status_call_args[1]["status"] == CJBatchStatusEnum.COMPLETE_INSUFFICIENT_ESSAYS

    mock_essay_repo.update_essay_scores_in_batch.assert_called()
    scores_call_args = mock_essay_repo.update_essay_scores_in_batch.call_args
    assert scores_call_args[1]["scores"]["student_1"] == 0.0

    event_publisher.publish_assessment_completed.assert_called_once()
    event_publisher.publish_assessment_result.assert_called_once()
    # Batch-level completion timestamp should be recorded for single-essay batches
    assert batch.completed_at is not None
