"""Unit tests for batch finalizer idempotency guards.

These tests verify that the idempotency guard in finalize_scoring() prevents
duplicate event publication when multiple triggers fire for the same batch.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from services.cj_assessment_service.cj_core_logic.batch_finalizer import BatchFinalizer
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_db import CJBatchUpload
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
    ContentClientProtocol,
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
        repo = AsyncMock(spec=CJRepositoryProtocol)
        event_publisher = AsyncMock(spec=CJEventPublisherProtocol)
        content_client = AsyncMock(spec=ContentClientProtocol)
        settings = Mock()

        batch = CJBatchUpload()
        batch.id = 42
        batch.bos_batch_id = "bos-42"
        batch.event_correlation_id = str(uuid4())
        batch.status = terminal_status  # Test all terminal states
        batch.created_at = datetime.now(UTC)
        batch.user_id = "user-123"
        batch.org_id = "org-abc"

        session = AsyncMock()
        session.get.return_value = batch

        finalizer = BatchFinalizer(
            database=repo,
            event_publisher=event_publisher,
            content_client=content_client,
            settings=settings,
        )

        # Act
        await finalizer.finalize_scoring(
            batch_id=batch.id,
            correlation_id=uuid4(),
            session=session,
            log_extra={},
        )

        # Assert: Should return early without calling any repository methods
        repo.get_essays_for_cj_batch.assert_not_called()
        repo.update_cj_batch_status.assert_not_called()
        event_publisher.publish_assessment_completed.assert_not_called()

    @pytest.mark.asyncio
    async def test_finalize_scoring_proceeds_when_not_terminal(self) -> None:
        """finalize_scoring should proceed normally when batch is in non-terminal state."""
        # This test verifies that the idempotency guard only blocks terminal states,
        # not valid states like PERFORMING_COMPARISONS
        # Arrange
        repo = AsyncMock(spec=CJRepositoryProtocol)
        event_publisher = AsyncMock(spec=CJEventPublisherProtocol)
        content_client = AsyncMock(spec=ContentClientProtocol)
        settings = Mock()

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

        session = AsyncMock()
        session.get.return_value = batch

        # Mock repository to return empty essays to avoid full scoring logic
        repo.get_essays_for_cj_batch.return_value = []
        repo.update_cj_batch_status = AsyncMock()

        finalizer = BatchFinalizer(
            database=repo,
            event_publisher=event_publisher,
            content_client=content_client,
            settings=settings,
        )

        # Act
        await finalizer.finalize_scoring(
            batch_id=batch.id,
            correlation_id=uuid4(),
            session=session,
            log_extra={},
        )

        # Assert: Should proceed with finalization logic
        # At minimum, it should call get_essays_for_cj_batch (proof it didn't return early)
        repo.get_essays_for_cj_batch.assert_called_once()
