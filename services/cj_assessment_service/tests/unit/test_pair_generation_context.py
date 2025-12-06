"""Tests for assessment context fetching in pair generation logic."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import AsyncContextManager, AsyncIterator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic import pair_generation
from services.cj_assessment_service.cj_core_logic.pair_generation import (
    PairGenerationMode,
    _fetch_assessment_context,
)
from services.cj_assessment_service.cj_core_logic.pair_orientation import (
    FairComplementOrientationStrategy,
)
from services.cj_assessment_service.cj_core_logic.prompt_templates import PromptTemplateBuilder
from services.cj_assessment_service.models_api import EssayForComparison
from services.cj_assessment_service.models_db import CJBatchUpload, ComparisonPair, ProcessedEssay
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    SessionProviderProtocol,
)
from services.cj_assessment_service.tests.helpers.matching_strategies import (
    make_real_matching_strategy_mock,
)
from services.cj_assessment_service.tests.helpers.positional_fairness import (
    get_positional_counts_for_batch,
)


class FakeResult:
    """Simple result wrapper emulating SQLAlchemy scalar response."""

    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


@pytest.mark.asyncio
async def test_fetch_assessment_context_uses_batch_assignment_when_metadata_missing() -> None:
    """Ensure assignment_id stored on batch is used when metadata lacks the value."""

    batch = SimpleNamespace(
        processing_metadata={"student_prompt_text": "Prompt from metadata"},
        assignment_id="assignment-001",
    )
    instruction = SimpleNamespace(instructions_text="Detailed assessment criteria")

    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[FakeResult(batch), FakeResult(instruction)],
    )

    result = await _fetch_assessment_context(session, cj_batch_id=42)

    assert result == {
        "assessment_instructions": "Detailed assessment criteria",
        "student_prompt_text": "Prompt from metadata",
        "judge_rubric_text": None,
    }
    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_fetch_assessment_context_returns_judge_rubric_from_metadata() -> None:
    """Ensure judge rubric text in metadata is surfaced in context payload."""

    batch = SimpleNamespace(
        processing_metadata={
            "student_prompt_text": "Prompt from metadata",
            "judge_rubric_text": "Judge rubric guidance",
        },
        assignment_id="assignment-002",
    )
    instruction = SimpleNamespace(instructions_text="Criteria text")

    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[FakeResult(batch), FakeResult(instruction)],
    )

    result = await _fetch_assessment_context(session, cj_batch_id=77)

    assert result == {
        "assessment_instructions": "Criteria text",
        "student_prompt_text": "Prompt from metadata",
        "judge_rubric_text": "Judge rubric guidance",
    }
    assert session.execute.await_count == 2


def test_build_comparison_prompt_orders_sections_correctly() -> None:
    """Verify comparison prompt includes all contextual sections in order."""

    essay_a = EssayForComparison(id="essay-a", text_content="Text A", current_bt_score=0.0)
    essay_b = EssayForComparison(id="essay-b", text_content="Text B", current_bt_score=0.0)

    prompt_blocks = PromptTemplateBuilder.assemble_full_prompt(
        {
            "assessment_instructions": "Assess clarity and structure.",
            "student_prompt_text": "Write about your summer.",
            "judge_rubric_text": "Prioritize originality and coherence.",
        },
        essay_a,
        essay_b,
    )
    prompt = PromptTemplateBuilder.render_prompt_text(prompt_blocks)

    assert "**Student Assignment:**" in prompt
    assert "**Assessment Criteria:**" in prompt
    assert "**Judge Instructions:**" in prompt
    assert "**Essay A (ID: essay-a):**" in prompt
    assert "**Essay B (ID: essay-b):**" in prompt

    student_index = prompt.index("**Student Assignment:**")
    criteria_index = prompt.index("**Assessment Criteria:**")
    judge_index = prompt.index("**Judge Instructions:**")
    essay_a_index = prompt.index("**Essay A (ID: essay-a):**")

    assert student_index < criteria_index < judge_index < essay_a_index


@pytest.mark.asyncio
async def test_fetch_assessment_context_detects_legacy_prompt() -> None:
    """Legacy prompt text should be reassigned to judge rubric and cleared from student prompt."""

    legacy_prompt = "You are an impartial comparative judgement assessor. Respond with JSON."
    batch = SimpleNamespace(
        processing_metadata={"student_prompt_text": legacy_prompt},
        assignment_id="assignment-legacy",
    )
    instruction = SimpleNamespace(instructions_text="Teacher rubric text")

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[FakeResult(batch), FakeResult(instruction)])

    result = await _fetch_assessment_context(session, cj_batch_id=512)

    assert result["student_prompt_text"] is None
    assert result["judge_rubric_text"] == legacy_prompt
    assert result["assessment_instructions"] == "Teacher rubric text"
    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_fetch_assessment_context_warns_when_instruction_missing() -> None:
    """Verify missing instructions returns None for both context fields.

    Note: Warning logs are emitted for observability but not asserted here to avoid
    brittle coupling to log format. Warnings can be verified manually in test output.
    """
    batch = SimpleNamespace(processing_metadata={}, assignment_id="assignment-404")

    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[FakeResult(batch), FakeResult(None)],
    )

    result = await _fetch_assessment_context(session, cj_batch_id=24)

    assert result == {
        "assessment_instructions": None,
        "student_prompt_text": None,
        "judge_rubric_text": None,
    }
    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_generate_comparison_tasks_respects_thresholds_and_global_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validate interplay between per-call threshold and global max comparisons."""

    global_cap = 4
    essays = [
        EssayForComparison(id="essay-a", text_content="Essay content A"),
        EssayForComparison(id="essay-b", text_content="Essay content B"),
        EssayForComparison(id="essay-c", text_content="Essay content C"),
        EssayForComparison(id="essay-d", text_content="Essay content D"),
    ]
    existing_pairs_store: set[tuple[str, str]] = set()

    async def fake_fetch_context(*_: object, **__: object) -> dict[str, str | None]:
        return {
            "assessment_instructions": "Assess clarity and structure.",
            "student_prompt_text": "Explain your argument.",
            "judge_rubric_text": None,
        }

    async def fake_fetch_existing_pairs(
        *_: object,
        **__: object,
    ) -> set[tuple[str, str]]:
        return set(existing_pairs_store)

    async def fake_fetch_counts(*_: object, **__: object) -> dict[str, int]:
        return {}

    async def fake_per_essay_counts(*_: object, **__: object) -> dict[str, tuple[int, int]]:
        return {}

    async def fake_per_pair_counts(
        *_: object, **__: object
    ) -> dict[tuple[str, str], tuple[int, int]]:
        return {}

    monkeypatch.setattr(pair_generation, "_fetch_assessment_context", fake_fetch_context)
    monkeypatch.setattr(
        pair_generation, "_fetch_existing_comparison_ids", fake_fetch_existing_pairs
    )
    monkeypatch.setattr(pair_generation, "_fetch_comparison_counts", fake_fetch_counts)
    monkeypatch.setattr(
        pair_generation,
        "_fetch_per_essay_position_counts",
        fake_per_essay_counts,
    )
    monkeypatch.setattr(
        pair_generation,
        "_fetch_per_pair_orientation_counts",
        fake_per_pair_counts,
    )

    def record_pairs(tasks: list) -> None:
        for task in tasks:
            existing_pairs_store.add(tuple(sorted((task.essay_a.id, task.essay_b.id))))

    AsyncMock(spec=AsyncSession)
    correlation_id = uuid4()
    matching_strategy = make_real_matching_strategy_mock()
    orientation_strategy = FairComplementOrientationStrategy()

    tasks_first_call = await pair_generation.generate_comparison_tasks(
        essays_for_comparison=essays,
        session_provider=AsyncMock(spec=SessionProviderProtocol),
        comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
        instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
        matching_strategy=matching_strategy,
        orientation_strategy=orientation_strategy,
        cj_batch_id=123,
        max_pairwise_comparisons=global_cap,
        correlation_id=correlation_id,
    )
    # Optimal matching returns one wave of pairs
    assert len(tasks_first_call) == len(essays) // 2
    record_pairs(tasks_first_call)

    tasks_second_call = await pair_generation.generate_comparison_tasks(
        essays_for_comparison=essays,
        session_provider=AsyncMock(spec=SessionProviderProtocol),
        comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
        instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
        matching_strategy=matching_strategy,
        orientation_strategy=orientation_strategy,
        cj_batch_id=123,
        max_pairwise_comparisons=global_cap,
        correlation_id=correlation_id,
    )
    # Second call should honour remaining global budget while avoiding duplicates
    assert len(tasks_second_call) == global_cap - len(tasks_first_call)
    record_pairs(tasks_second_call)

    tasks_third_call = await pair_generation.generate_comparison_tasks(
        essays_for_comparison=essays,
        session_provider=AsyncMock(spec=SessionProviderProtocol),
        comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
        instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
        matching_strategy=matching_strategy,
        orientation_strategy=orientation_strategy,
        cj_batch_id=123,
        max_pairwise_comparisons=global_cap,
        correlation_id=correlation_id,
    )
    assert tasks_third_call == []
    assert len(existing_pairs_store) == global_cap


@pytest.mark.asyncio
async def test_resampling_mode_uses_existing_pairs_and_balances_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RESAMPLING mode should only use existing pairs and keep essay counts balanced.

    This simulates multiple resampling waves where all essays should receive
    a comparable number of additional comparisons over time.
    """

    essays = [
        EssayForComparison(id="essay-a", text_content="Essay content A"),
        EssayForComparison(id="essay-b", text_content="Essay content B"),
        EssayForComparison(id="essay-c", text_content="Essay content C"),
    ]
    essay_ids = {essay.id for essay in essays}

    # Simulate Phase-1 coverage having produced all unordered pairs.
    existing_pairs_store: set[tuple[str, str]] = set()
    for i, essay_a in enumerate(essays):
        for essay_b in essays[i + 1 :]:
            normalized_pair: tuple[str, str] = tuple(sorted((essay_a.id, essay_b.id)))  # type: ignore[assignment]
            existing_pairs_store.add(normalized_pair)

    # Track comparison counts across resampling waves (per essay).
    comparison_counts_store: dict[str, int] = {essay_id: 0 for essay_id in essay_ids}

    async def fake_fetch_context(*_: object, **__: object) -> dict[str, str | None]:
        return {
            "assessment_instructions": "Assess clarity and structure.",
            "student_prompt_text": "Explain your argument.",
            "judge_rubric_text": None,
        }

    async def fake_fetch_existing_pairs(
        *_: object,
        **__: object,
    ) -> set[tuple[str, str]]:
        # Always resample from the same existing Phase-1 pairs.
        return set(existing_pairs_store)

    async def fake_fetch_counts(*_: object, **__: object) -> dict[str, int]:
        # Return the evolving comparison counts for fairness scoring.
        return dict(comparison_counts_store)

    async def fake_per_essay_counts(*_: object, **__: object) -> dict[str, tuple[int, int]]:
        return {}

    async def fake_per_pair_counts(
        *_: object, **__: object
    ) -> dict[tuple[str, str], tuple[int, int]]:
        return {}

    monkeypatch.setattr(pair_generation, "_fetch_assessment_context", fake_fetch_context)
    monkeypatch.setattr(
        pair_generation, "_fetch_existing_comparison_ids", fake_fetch_existing_pairs
    )
    monkeypatch.setattr(pair_generation, "_fetch_comparison_counts", fake_fetch_counts)
    monkeypatch.setattr(
        pair_generation,
        "_fetch_per_essay_position_counts",
        fake_per_essay_counts,
    )
    monkeypatch.setattr(
        pair_generation,
        "_fetch_per_pair_orientation_counts",
        fake_per_pair_counts,
    )

    AsyncMock(spec=AsyncSession)
    matching_strategy = make_real_matching_strategy_mock()
    orientation_strategy = FairComplementOrientationStrategy()

    # Run several resampling waves and ensure counts stay balanced.
    num_waves = 5
    for _ in range(num_waves):
        tasks = await pair_generation.generate_comparison_tasks(
            essays_for_comparison=essays,
            session_provider=AsyncMock(spec=SessionProviderProtocol),
            comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
            instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
            matching_strategy=matching_strategy,
            orientation_strategy=orientation_strategy,
            cj_batch_id=999,
            # No explicit cap here; we are testing fairness of resampling selection.
            max_pairwise_comparisons=None,
            correlation_id=None,
            randomization_seed=123,
            mode=PairGenerationMode.RESAMPLING,
        )

        # All pairs must involve only the original essay IDs.
        assert tasks, "Expected RESAMPLING to yield comparison tasks"
        for task in tasks:
            assert task.essay_a.id in essay_ids
            assert task.essay_b.id in essay_ids

            comparison_counts_store[task.essay_a.id] += 1
            comparison_counts_store[task.essay_b.id] += 1

    counts = list(comparison_counts_store.values())
    # Every essay should have been sampled at least once.
    assert min(counts) > 0
    # Fairness guardrail: RESAMPLING should not starve any essay.
    assert max(counts) - min(counts) <= 2


@pytest.mark.asyncio
async def test_resampling_positional_skew_stays_within_band(
    monkeypatch: pytest.MonkeyPatch,
    postgres_session: AsyncSession,
) -> None:
    """RESAMPLING waves should keep per-essay A/B positional skew bounded."""

    essays = [
        EssayForComparison(id="essay-a", text_content="Essay content A"),
        EssayForComparison(id="essay-b", text_content="Essay content B"),
        EssayForComparison(id="essay-c", text_content="Essay content C"),
    ]
    essay_ids = {essay.id for essay in essays}

    # Create a small CJ batch and corresponding ProcessedEssay rows for DB-backed
    # positional counts. Pair generation itself operates on the in-memory
    # EssayForComparison objects above.
    batch = CJBatchUpload(
        bos_batch_id="bos-positional-resampling",
        event_correlation_id="00000000-0000-0000-0000-000000000020",
        language="en",
        course_code="eng5",
        expected_essay_count=len(essays),
        status=None,
    )
    postgres_session.add(batch)
    await postgres_session.flush()

    for essay in essays:
        postgres_session.add(
            ProcessedEssay(
                els_essay_id=essay.id,
                cj_batch_id=batch.id,
                text_storage_id=f"storage-{essay.id}",
                assessment_input_text=essay.text_content,
                current_bt_score=0.0,
                current_bt_se=None,
                comparison_count=0,
                is_anchor=False,
            )
        )
    await postgres_session.flush()

    # Simulate Phase-1 coverage having produced all unordered pairs.
    existing_pairs_store: set[tuple[str, str]] = set()
    for i, essay_a in enumerate(essays):
        for essay_b in essays[i + 1 :]:
            normalized_pair: tuple[str, str] = tuple(sorted((essay_a.id, essay_b.id)))  # type: ignore[assignment]
            existing_pairs_store.add(normalized_pair)

    comparison_counts_store: dict[str, int] = {essay_id: 0 for essay_id in essay_ids}

    async def fake_fetch_context(*_: object, **__: object) -> dict[str, str | None]:
        return {
            "assessment_instructions": "Assess clarity and structure.",
            "student_prompt_text": "Explain your argument.",
            "judge_rubric_text": None,
        }

    async def fake_fetch_existing_pairs(
        *_: object,
        **__: object,
    ) -> set[tuple[str, str]]:
        return set(existing_pairs_store)

    async def fake_fetch_counts(*_: object, **__: object) -> dict[str, int]:
        return dict(comparison_counts_store)

    monkeypatch.setattr(pair_generation, "_fetch_assessment_context", fake_fetch_context)
    monkeypatch.setattr(
        pair_generation, "_fetch_existing_comparison_ids", fake_fetch_existing_pairs
    )
    monkeypatch.setattr(pair_generation, "_fetch_comparison_counts", fake_fetch_counts)

    matching_strategy = make_real_matching_strategy_mock()
    orientation_strategy = FairComplementOrientationStrategy()

    @asynccontextmanager
    async def _session_ctx() -> AsyncIterator[AsyncSession]:
        yield postgres_session

    class _SessionProvider:
        def session(self) -> AsyncContextManager[AsyncSession]:
            return _session_ctx()

    session_provider = _SessionProvider()

    num_waves = 5
    for wave_index in range(num_waves):
        tasks = await pair_generation.generate_comparison_tasks(
            essays_for_comparison=essays,
            session_provider=session_provider,
            comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
            instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
            matching_strategy=matching_strategy,
            orientation_strategy=orientation_strategy,
            cj_batch_id=batch.id,
            max_pairwise_comparisons=None,
            correlation_id=None,
            randomization_seed=123 + wave_index,
            mode=PairGenerationMode.RESAMPLING,
        )

        assert tasks, "Expected RESAMPLING to yield comparison tasks"
        for task in tasks:
            assert task.essay_a.id in essay_ids
            assert task.essay_b.id in essay_ids

            comparison_counts_store[task.essay_a.id] += 1
            comparison_counts_store[task.essay_b.id] += 1

            postgres_session.add(
                ComparisonPair(
                    cj_batch_id=batch.id,
                    essay_a_els_id=task.essay_a.id,
                    essay_b_els_id=task.essay_b.id,
                    prompt_text="prompt",
                    winner=None,
                    confidence=None,
                    justification=None,
                    raw_llm_response=None,
                    error_code=None,
                    error_correlation_id=None,
                    error_timestamp=None,
                    error_service=None,
                    error_details=None,
                )
            )

    await postgres_session.flush()

    positional_counts = await get_positional_counts_for_batch(
        session=postgres_session,
        cj_batch_id=batch.id,
    )

    # Compute per-essay positional skew and enforce an initial LOWER5-style band.
    MAX_ALLOWED_SKEW = 0.5  # Generous initial bound; to be tightened with traces.
    for essay_id in essay_ids:
        counts = positional_counts.get(essay_id, {"A": 0, "B": 0})
        a_count = counts["A"]
        b_count = counts["B"]
        total = a_count + b_count
        assert total > 0
        skew = abs(a_count - b_count) / total
        assert skew <= MAX_ALLOWED_SKEW
