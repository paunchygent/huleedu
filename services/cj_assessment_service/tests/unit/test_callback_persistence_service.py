"""Unit tests for CallbackPersistenceService orchestration behaviors."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core.domain_enums import EssayComparisonWinner
from common_core.error_enums import ErrorCode

from services.cj_assessment_service.cj_core_logic.batch_completion_policy import (
    BatchCompletionPolicy,
)
from services.cj_assessment_service.cj_core_logic.callback_persistence_service import (
    CallbackPersistenceService,
)
from services.cj_assessment_service.cj_core_logic.callback_retry_coordinator import (
    ComparisonRetryCoordinator,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_db import ComparisonPair
from services.cj_assessment_service.tests.unit.test_callback_state_manager import (
    MockSession,
    create_comparison_pair,
    create_llm_comparison_result,
)


@pytest.fixture
def completion_policy() -> AsyncMock:
    return AsyncMock(spec=BatchCompletionPolicy)


@pytest.fixture
def retry_coordinator() -> AsyncMock:
    return AsyncMock(spec=ComparisonRetryCoordinator)


@pytest.fixture
def service(
    completion_policy: AsyncMock,
    retry_coordinator: AsyncMock,
) -> CallbackPersistenceService:
    return CallbackPersistenceService(
        completion_policy=completion_policy,
        retry_coordinator=retry_coordinator,
    )


@pytest.fixture
def comparison_pair() -> ComparisonPair:
    return create_comparison_pair()


@pytest.fixture
def mock_comparison_repository(comparison_pair: ComparisonPair) -> AsyncMock:
    """Create mock comparison repository."""
    repo = AsyncMock()
    repo.get_comparison_pair_by_correlation_id = AsyncMock(return_value=comparison_pair)
    return repo


@pytest.fixture
def mock_batch_repository() -> AsyncMock:
    """Create mock batch repository."""
    return AsyncMock()


class TestUpdateComparisonResult:
    """Behavioral tests for update_comparison_result orchestrator."""

    @pytest.fixture
    def settings(self) -> Mock:
        s = Mock(spec=Settings)
        s.ENABLE_FAILED_COMPARISON_RETRY = False
        return s

    @pytest.mark.asyncio
    async def test_idempotent_when_winner_already_set(
        self,
        service: CallbackPersistenceService,
        comparison_pair: ComparisonPair,
        completion_policy: AsyncMock,
        retry_coordinator: AsyncMock,
        settings: Mock,
    ) -> None:
        correlation_id = uuid4()
        comparison_pair.winner = "essay_a"
        comparison_pair.request_correlation_id = correlation_id
        session = MockSession(comparison_pair=comparison_pair)

        # Create mock repositories
        comparison_repository = AsyncMock()
        comparison_repository.get_comparison_pair_by_correlation_id = AsyncMock(
            return_value=comparison_pair
        )
        batch_repository = AsyncMock()

        result = await service.update_comparison_result(
            comparison_result=Mock(),  # winner already set, callback ignored
            session=session,  # type: ignore[arg-type]
            comparison_repository=comparison_repository,
            batch_repository=batch_repository,
            correlation_id=correlation_id,
            settings=settings,
        )

        assert result == comparison_pair.cj_batch_id
        completion_policy.update_batch_completion_counters.assert_not_awaited()
        retry_coordinator.add_failed_comparison_to_pool.assert_not_awaited()
        retry_coordinator.handle_successful_retry.assert_not_awaited()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_success_callback_updates_fields_and_calls_completion_counters(
        self,
        service: CallbackPersistenceService,
        completion_policy: AsyncMock,
        retry_coordinator: AsyncMock,
        settings: Mock,
    ) -> None:
        correlation_id = uuid4()
        comparison_pair = create_comparison_pair(request_correlation_id=correlation_id, winner=None)
        session = MockSession(comparison_pair=comparison_pair)

        # Create mock repositories
        comparison_repository = AsyncMock()
        comparison_repository.get_comparison_pair_by_correlation_id = AsyncMock(
            return_value=comparison_pair
        )
        batch_repository = AsyncMock()

        comparison_result = create_llm_comparison_result(
            correlation_id=correlation_id,
            winner=EssayComparisonWinner.ESSAY_B,
            confidence=3.3,
            justification="B wins",
        )

        result_batch_id = await service.update_comparison_result(
            comparison_result=comparison_result,
            session=session,  # type: ignore[arg-type]
            comparison_repository=comparison_repository,
            batch_repository=batch_repository,
            correlation_id=correlation_id,
            settings=settings,
        )

        assert result_batch_id == comparison_pair.cj_batch_id
        assert comparison_pair.winner == "essay_b"
        assert comparison_pair.confidence == 3.3
        assert comparison_pair.justification == "B wins"
        processing_metadata = comparison_pair.processing_metadata
        assert processing_metadata is not None
        assert processing_metadata["provider"] == comparison_result.provider.value
        completion_policy.update_batch_completion_counters.assert_awaited_once()
        kwargs = completion_policy.update_batch_completion_counters.await_args.kwargs
        assert kwargs["is_error"] is False
        assert kwargs["batch_repo"] is batch_repository
        assert kwargs["session"] is session
        session.commit.assert_awaited_once()
        retry_coordinator.handle_successful_retry.assert_not_awaited()
        retry_coordinator.add_failed_comparison_to_pool.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_success_callback_with_retry_enabled_calls_handle_successful_retry(
        self,
        service: CallbackPersistenceService,
        completion_policy: AsyncMock,
        retry_coordinator: AsyncMock,
        settings: Mock,
    ) -> None:
        correlation_id = uuid4()
        comparison_pair = create_comparison_pair(request_correlation_id=correlation_id, winner=None)
        session = MockSession(comparison_pair=comparison_pair)

        # Create mock repositories
        comparison_repository = AsyncMock()
        comparison_repository.get_comparison_pair_by_correlation_id = AsyncMock(
            return_value=comparison_pair
        )
        batch_repository = AsyncMock()

        comparison_result = create_llm_comparison_result(
            correlation_id=correlation_id, winner=EssayComparisonWinner.ESSAY_A
        )

        settings.ENABLE_FAILED_COMPARISON_RETRY = True
        pool_manager = AsyncMock()

        await service.update_comparison_result(
            comparison_result=comparison_result,
            session=session,  # type: ignore[arg-type]
            comparison_repository=comparison_repository,
            batch_repository=batch_repository,
            correlation_id=correlation_id,
            settings=settings,
            pool_manager=pool_manager,
        )

        retry_coordinator.handle_successful_retry.assert_awaited_once()
        retry_coordinator.add_failed_comparison_to_pool.assert_not_awaited()
        completion_policy.update_batch_completion_counters.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_error_callback_persists_error_and_calls_retry_when_enabled(
        self,
        service: CallbackPersistenceService,
        completion_policy: AsyncMock,
        retry_coordinator: AsyncMock,
        settings: Mock,
    ) -> None:
        correlation_id = uuid4()
        comparison_pair = create_comparison_pair(request_correlation_id=correlation_id, winner=None)
        session = MockSession(comparison_pair=comparison_pair)

        # Create mock repositories
        comparison_repository = AsyncMock()
        comparison_repository.get_comparison_pair_by_correlation_id = AsyncMock(
            return_value=comparison_pair
        )
        batch_repository = AsyncMock()

        comparison_result = create_llm_comparison_result(
            correlation_id=correlation_id,
            is_error=True,
            winner=None,
        )

        settings.ENABLE_FAILED_COMPARISON_RETRY = True
        pool_manager = AsyncMock()
        retry_processor = AsyncMock()

        await service.update_comparison_result(
            comparison_result=comparison_result,
            session=session,  # type: ignore[arg-type]
            comparison_repository=comparison_repository,
            batch_repository=batch_repository,
            correlation_id=correlation_id,
            settings=settings,
            pool_manager=pool_manager,
            retry_processor=retry_processor,
        )

        assert comparison_pair.winner == "error"
        error_detail = comparison_result.error_detail
        assert error_detail is not None
        assert comparison_pair.error_code == error_detail.error_code.value
        retry_coordinator.add_failed_comparison_to_pool.assert_awaited_once()
        retry_coordinator.handle_successful_retry.assert_not_awaited()
        completion_policy.update_batch_completion_counters.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_malformed_error_is_persisted_without_retry(
        self,
        service: CallbackPersistenceService,
        completion_policy: AsyncMock,
        retry_coordinator: AsyncMock,
        settings: Mock,
    ) -> None:
        correlation_id = uuid4()
        comparison_pair = create_comparison_pair(request_correlation_id=correlation_id, winner=None)
        session = MockSession(comparison_pair=comparison_pair)

        # Create mock repositories
        comparison_repository = AsyncMock()
        comparison_repository.get_comparison_pair_by_correlation_id = AsyncMock(
            return_value=comparison_pair
        )
        batch_repository = AsyncMock()

        class MalformedResult:
            is_error = True
            error_detail = None
            completed_at = datetime.now(UTC)
            request_id = "req-123"

        settings.ENABLE_FAILED_COMPARISON_RETRY = True

        comparison_result = MalformedResult()

        result_batch_id = await service.update_comparison_result(
            comparison_result=comparison_result,
            session=session,  # type: ignore[arg-type]
            comparison_repository=comparison_repository,
            batch_repository=batch_repository,
            correlation_id=correlation_id,
            settings=settings,
            pool_manager=AsyncMock(),
            retry_processor=AsyncMock(),
        )

        assert result_batch_id == comparison_pair.cj_batch_id
        assert comparison_pair.winner == "error"
        assert comparison_pair.error_code == ErrorCode.INVALID_RESPONSE.value
        completion_policy.update_batch_completion_counters.assert_awaited_once()
        retry_coordinator.add_failed_comparison_to_pool.assert_not_awaited()
        retry_coordinator.handle_successful_retry.assert_not_awaited()
        session.commit.assert_awaited_once()
