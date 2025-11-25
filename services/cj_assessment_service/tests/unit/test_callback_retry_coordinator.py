"""Unit tests for ComparisonRetryCoordinator retry pool behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.cj_assessment_service.cj_core_logic.callback_retry_coordinator import (
    ComparisonRetryCoordinator,
)
from services.cj_assessment_service.models_api import (
    ComparisonTask,
    EssayForComparison,
    FailedComparisonEntry,
    FailedComparisonPool,
)
from services.cj_assessment_service.models_db import ComparisonPair


@pytest.fixture
def comparison_pair() -> ComparisonPair:
    pair = ComparisonPair()
    pair.id = 42
    pair.cj_batch_id = 7
    pair.essay_a_els_id = "essay-a"
    pair.essay_b_els_id = "essay-b"
    pair.prompt_text = "Compare these essays"
    return pair


@pytest.fixture
def coordinator() -> ComparisonRetryCoordinator:
    return ComparisonRetryCoordinator()


class _ErrorDetail:
    def __init__(self, value: str) -> None:
        self.error_code = type("obj", (), {"value": value})
        self.details = {"provider": "anthropic"}


class _ComparisonResult:
    def __init__(self, error_code_value: str = "LLM_PROVIDER_TIMEOUT") -> None:
        self.error_detail = _ErrorDetail(error_code_value)


class TestAddFailedComparisonToPool:
    """Tests for add_failed_comparison_to_pool."""

    @pytest.mark.asyncio
    async def test_adds_to_pool_and_triggers_retry_when_needed(
        self,
        coordinator: ComparisonRetryCoordinator,
        comparison_pair: ComparisonPair,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool_manager = AsyncMock()
        retry_processor = AsyncMock()
        comparison_result = _ComparisonResult()

        monkeypatch.setattr(
            coordinator,
            "reconstruct_comparison_task",
            AsyncMock(
                return_value=ComparisonTask(
                    essay_a=EssayForComparison(id="essay-a", text_content="[a]"),
                    essay_b=EssayForComparison(id="essay-b", text_content="[b]"),
                    prompt=comparison_pair.prompt_text,
                )
            ),
        )

        pool_manager.check_retry_batch_needed.return_value = True

        await coordinator.add_failed_comparison_to_pool(
            pool_manager=pool_manager,
            retry_processor=retry_processor,
            comparison_pair=comparison_pair,
            comparison_result=comparison_result,
            correlation_id=uuid4(),
        )

        pool_manager.add_to_failed_pool.assert_awaited_once()
        pool_manager.check_retry_batch_needed.assert_awaited_once()
        retry_processor.submit_retry_batch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retry_not_triggered_when_not_needed(
        self,
        coordinator: ComparisonRetryCoordinator,
        comparison_pair: ComparisonPair,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool_manager = AsyncMock()
        retry_processor = AsyncMock()

        monkeypatch.setattr(
            coordinator,
            "reconstruct_comparison_task",
            AsyncMock(return_value=AsyncMock(spec=ComparisonTask)),
        )
        pool_manager.check_retry_batch_needed.return_value = False

        await coordinator.add_failed_comparison_to_pool(
            pool_manager=pool_manager,
            retry_processor=retry_processor,
            comparison_pair=comparison_pair,
            comparison_result=_ComparisonResult(),
            correlation_id=uuid4(),
        )

        pool_manager.add_to_failed_pool.assert_awaited_once()
        retry_processor.submit_retry_batch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reconstruct_none_exits_early(
        self,
        coordinator: ComparisonRetryCoordinator,
        comparison_pair: ComparisonPair,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool_manager = AsyncMock()
        retry_processor = AsyncMock()
        monkeypatch.setattr(
            coordinator,
            "reconstruct_comparison_task",
            AsyncMock(return_value=None),
        )

        await coordinator.add_failed_comparison_to_pool(
            pool_manager=pool_manager,
            retry_processor=retry_processor,
            comparison_pair=comparison_pair,
            comparison_result=_ComparisonResult(),
            correlation_id=uuid4(),
        )

        pool_manager.add_to_failed_pool.assert_not_awaited()
        pool_manager.check_retry_batch_needed.assert_not_awaited()
        retry_processor.submit_retry_batch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pool_errors_are_swallowed(
        self,
        coordinator: ComparisonRetryCoordinator,
        comparison_pair: ComparisonPair,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool_manager = AsyncMock()
        retry_processor = AsyncMock()

        monkeypatch.setattr(
            coordinator,
            "reconstruct_comparison_task",
            AsyncMock(return_value=AsyncMock(spec=ComparisonTask)),
        )
        pool_manager.add_to_failed_pool.side_effect = RuntimeError("boom")

        await coordinator.add_failed_comparison_to_pool(
            pool_manager=pool_manager,
            retry_processor=retry_processor,
            comparison_pair=comparison_pair,
            comparison_result=_ComparisonResult(),
            correlation_id=uuid4(),
        )

        pool_manager.check_retry_batch_needed.assert_not_awaited()
        retry_processor.submit_retry_batch.assert_not_awaited()


class _DummyCounter:
    def __init__(self) -> None:
        self.inc_calls = 0
        self.set_calls: list[tuple[str, int]] = []
        self._labels: dict[str, str] | None = None

    def inc(self) -> None:  # pragma: no cover - trivial
        self.inc_calls += 1

    def labels(self, **labels: str) -> "_DummyCounter":  # pragma: no cover - trivial
        self._labels = labels
        return self

    def set(self, value: int) -> None:  # pragma: no cover - trivial
        assert self._labels is not None
        self.set_calls.append((self._labels["batch_id"], value))


class TestHandleSuccessfulRetry:
    """Tests for handle_successful_retry behavior."""

    @pytest.mark.asyncio
    async def test_removes_entry_updates_stats_and_merges_metadata(
        self,
        coordinator: ComparisonRetryCoordinator,
        comparison_pair: ComparisonPair,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Build pool with one entry to remove
        entry = FailedComparisonEntry(
            essay_a_id=comparison_pair.essay_a_els_id,
            essay_b_id=comparison_pair.essay_b_els_id,
            comparison_task=ComparisonTask(
                essay_a=EssayForComparison(id="essay-a", text_content="[a]"),
                essay_b=EssayForComparison(id="essay-b", text_content="[b]"),
                prompt=comparison_pair.prompt_text,
            ),
            failure_reason="timeout",
            failed_at=datetime.now(UTC),
            retry_count=0,
            original_batch_id=str(comparison_pair.cj_batch_id),
            correlation_id=uuid4(),
        )
        pool = FailedComparisonPool(failed_comparison_pool=[entry])

        class _BatchState:
            def __init__(self) -> None:
                self.cj_batch_id = comparison_pair.cj_batch_id
                self.processing_metadata = pool.model_dump(mode="json")

        batch_state = _BatchState()

        # Mock DB session context
        db_session = AsyncMock()

        class _SessionCM:
            def __init__(self, session: Any) -> None:
                self._session = session

            async def __aenter__(self) -> Any:
                return self._session

            async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
                return None

        class _Database:
            def session(self) -> "_SessionCM":
                return _SessionCM(db_session)

        pool_manager = AsyncMock()
        pool_manager.database = _Database()

        # Monkeypatch collaborators
        async def _get_batch_state(*_: Any, **__: Any) -> Any:
            return batch_state

        merge_mock = AsyncMock()

        monkeypatch.setattr(
            "services.cj_assessment_service.cj_core_logic.batch_submission.get_batch_state",
            _get_batch_state,
        )
        monkeypatch.setattr(
            "services.cj_assessment_service.cj_core_logic.batch_submission.merge_batch_processing_metadata",
            merge_mock,
        )

        successful_counter = _DummyCounter()
        pool_size_gauge = _DummyCounter()

        monkeypatch.setattr(
            "services.cj_assessment_service.metrics.get_business_metrics",
            lambda: {
                "cj_successful_retries_total": successful_counter,
                "cj_failed_pool_size": pool_size_gauge,
            },
        )

        await coordinator.handle_successful_retry(
            pool_manager=pool_manager,
            comparison_pair=comparison_pair,
            correlation_id=uuid4(),
        )

        assert pool_size_gauge.set_calls in (
            [(str(comparison_pair.cj_batch_id), 0)],
            [],
        )
        await_args = merge_mock.await_args
        assert await_args is not None
        merge_kwargs = await_args.kwargs
        assert merge_kwargs["cj_batch_id"] == comparison_pair.cj_batch_id
        assert merge_kwargs["metadata_updates"]["pool_statistics"]["successful_retries"] == 1
        assert merge_kwargs["metadata_updates"]["failed_comparison_pool"] == []

    @pytest.mark.parametrize(
        "batch_state,expect_merge",
        [
            (None, False),  # missing batch state
            (type("obj", (), {"processing_metadata": None}), False),  # missing metadata
        ],
    )
    @pytest.mark.asyncio
    async def test_noop_when_state_missing_or_metadata_absent(
        self,
        coordinator: ComparisonRetryCoordinator,
        comparison_pair: ComparisonPair,
        batch_state: Any,
        expect_merge: bool,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool_manager = AsyncMock()

        class _DummySession:
            pass

        dummy_session = _DummySession()

        class _SessionCM:
            def __init__(self, session: Any) -> None:
                self._session = session

            async def __aenter__(self) -> Any:
                return self._session

            async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
                return None

        class _Database:
            def session(self) -> "_SessionCM":
                return _SessionCM(dummy_session)

        pool_manager.database = _Database()

        async def _get_batch_state(*_: Any, **__: Any) -> Any:
            return batch_state

        merge_mock = AsyncMock()

        monkeypatch.setattr(
            "services.cj_assessment_service.cj_core_logic.batch_submission.get_batch_state",
            _get_batch_state,
        )
        monkeypatch.setattr(
            "services.cj_assessment_service.cj_core_logic.batch_submission.merge_batch_processing_metadata",
            merge_mock,
        )
        monkeypatch.setattr(
            "services.cj_assessment_service.metrics.get_business_metrics",
            lambda: {},
        )

        await coordinator.handle_successful_retry(
            pool_manager=pool_manager,
            comparison_pair=comparison_pair,
            correlation_id=uuid4(),
        )

        if expect_merge:
            merge_mock.assert_awaited()
        else:
            merge_mock.assert_not_awaited()


class TestReconstructComparisonTask:
    """Tests for reconstruct_comparison_task."""

    @pytest.mark.asyncio
    async def test_reconstructs_task(
        self, coordinator: ComparisonRetryCoordinator, comparison_pair: ComparisonPair
    ) -> None:
        task = await coordinator.reconstruct_comparison_task(
            comparison_pair=comparison_pair,
            correlation_id=uuid4(),
        )

        assert isinstance(task, ComparisonTask)
        assert task.prompt == comparison_pair.prompt_text
        assert task.essay_a.id == comparison_pair.essay_a_els_id
        assert task.essay_b.id == comparison_pair.essay_b_els_id

    @pytest.mark.asyncio
    async def test_reconstruct_returns_none_on_exception(
        self,
        coordinator: ComparisonRetryCoordinator,
        comparison_pair: ComparisonPair,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _explode(*_: Any, **__: Any) -> Any:
            raise RuntimeError("bad data")

        monkeypatch.setattr(
            "services.cj_assessment_service.cj_core_logic.callback_retry_coordinator.EssayForComparison",
            _explode,
        )

        result = await coordinator.reconstruct_comparison_task(
            comparison_pair=comparison_pair,
            correlation_id=uuid4(),
        )

        assert result is None
