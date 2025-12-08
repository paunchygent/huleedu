"""Unit tests for batch finalizer idempotency guards.

These tests verify that the idempotency guard in finalize_scoring() prevents
duplicate event publication when multiple triggers fire for the same batch.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.batch_finalizer import BatchFinalizer
from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_db import CJBatchUpload
from services.cj_assessment_service.protocols import (
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    CJEssayRepositoryProtocol,
    CJEventPublisherProtocol,
    ContentClientProtocol,
    SessionProviderProtocol,
)


class TestFinalizeScoringIdempotency:
    """Tests for finalize_scoring idempotency guard."""

    @pytest.mark.parametrize(
        "terminal_status",
        [
            CJBatchStatusEnum.COMPLETE_STABLE,
            CJBatchStatusEnum.COMPLETE_MAX_COMPARISONS,
            CJBatchStatusEnum.COMPLETE_INSUFFICIENT_ESSAYS,
            CJBatchStatusEnum.ERROR_PROCESSING,
            CJBatchStatusEnum.ERROR_ESSAY_PROCESSING,
        ],
    )
    @pytest.mark.asyncio
    async def test_finalize_scoring_skips_terminal_states(
        self, terminal_status: CJBatchStatusEnum
    ) -> None:
        """finalize_scoring should return early for all terminal states."""
        # Arrange
        session_provider = AsyncMock(spec=SessionProviderProtocol)
        batch_repo = AsyncMock(spec=CJBatchRepositoryProtocol)
        essay_repo = AsyncMock(spec=CJEssayRepositoryProtocol)
        event_publisher = AsyncMock(spec=CJEventPublisherProtocol)
        content_client = AsyncMock(spec=ContentClientProtocol)
        settings = Mock()
        grade_projector = AsyncMock(spec=GradeProjector)

        batch = CJBatchUpload()
        batch.id = 42
        batch.bos_batch_id = "bos-42"
        batch.event_correlation_id = str(uuid4())
        batch.status = terminal_status  # Test all terminal states
        batch.created_at = datetime.now(UTC)
        batch.user_id = "user-123"
        batch.org_id = "org-abc"
        batch.completed_at = datetime.now(UTC)

        session = AsyncMock(spec=AsyncSession)
        session.get.return_value = batch
        session_provider.session.return_value.__aenter__.return_value = session
        session_provider.session.return_value.__aexit__.return_value = None

        finalizer = BatchFinalizer(
            session_provider=session_provider,
            batch_repository=batch_repo,
            comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
            essay_repository=essay_repo,
            event_publisher=event_publisher,
            content_client=content_client,
            settings=settings,
            grade_projector=grade_projector,
        )

        # Act
        await finalizer.finalize_scoring(
            batch_id=batch.id,
            correlation_id=uuid4(),
            log_extra={},
        )

        # Assert: Should return early without calling any repository methods
        essay_repo.get_essays_for_cj_batch.assert_not_called()
        batch_repo.update_cj_batch_status.assert_not_called()
        event_publisher.publish_assessment_completed.assert_not_called()

    @pytest.mark.asyncio
    async def test_finalize_scoring_proceeds_when_not_terminal(self) -> None:
        """finalize_scoring should proceed normally when batch is in non-terminal state."""
        # This test verifies that the idempotency guard only blocks terminal states,
        # not valid states like PERFORMING_COMPARISONS
        # Arrange
        session_provider = AsyncMock(spec=SessionProviderProtocol)
        batch_repo = AsyncMock(spec=CJBatchRepositoryProtocol)
        essay_repo = AsyncMock(spec=CJEssayRepositoryProtocol)
        event_publisher = AsyncMock(spec=CJEventPublisherProtocol)
        content_client = AsyncMock(spec=ContentClientProtocol)
        settings = Mock()
        grade_projector = AsyncMock(spec=GradeProjector)

        batch = CJBatchUpload()
        batch.id = 42
        batch.bos_batch_id = "bos-42"
        batch.event_correlation_id = str(uuid4())
        batch.status = CJBatchStatusEnum.PERFORMING_COMPARISONS  # Non-terminal state
        batch.language = "en"
        batch.course_code = "ENG5"
        batch.expected_essay_count = 2
        batch.created_at = datetime.now(UTC)
        batch.user_id = "user-123"
        batch.org_id = "org-abc"
        batch.assignment_id = "assignment-xyz"

        session = AsyncMock(spec=AsyncSession)
        session.get.return_value = batch
        session_provider.session.return_value.__aenter__.return_value = session
        session_provider.session.return_value.__aexit__.return_value = None

        # Mock repository to return empty essays to avoid full scoring logic
        essay_repo.get_essays_for_cj_batch.return_value = []
        batch_repo.update_cj_batch_status = AsyncMock()

        finalizer = BatchFinalizer(
            session_provider=session_provider,
            batch_repository=batch_repo,
            comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
            essay_repository=essay_repo,
            event_publisher=event_publisher,
            content_client=content_client,
            settings=settings,
            grade_projector=grade_projector,
        )

        # Act
        await finalizer.finalize_scoring(
            batch_id=batch.id,
            correlation_id=uuid4(),
            log_extra={},
        )

        # Assert: Should proceed with finalization logic
        # At minimum, it should call get_essays_for_cj_batch (proof it didn't return early)
        essay_repo.get_essays_for_cj_batch.assert_called_once()
