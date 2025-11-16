"""Tests for assessment context fetching in pair generation logic."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic import pair_generation
from services.cj_assessment_service.cj_core_logic.pair_generation import (
    _build_comparison_prompt,
    _fetch_assessment_context,
)
from services.cj_assessment_service.models_api import EssayForComparison


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

    prompt = _build_comparison_prompt(
        essay_a=essay_a,
        essay_b=essay_b,
        assessment_instructions="Assess clarity and structure.",
        student_prompt_text="Write about your summer.",
        judge_rubric_text="Prioritize originality and coherence.",
    )

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

    per_call_threshold = 3
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

    monkeypatch.setattr(pair_generation, "_fetch_assessment_context", fake_fetch_context)
    monkeypatch.setattr(
        pair_generation,
        "_fetch_existing_comparison_ids",
        fake_fetch_existing_pairs,
    )

    def record_pairs(tasks: list) -> None:
        for task in tasks:
            existing_pairs_store.add(tuple(sorted((task.essay_a.id, task.essay_b.id))))

    session = AsyncMock(spec=AsyncSession)
    correlation_id = uuid4()

    tasks_first_call = await pair_generation.generate_comparison_tasks(
        essays_for_comparison=essays,
        db_session=session,
        cj_batch_id=123,
        existing_pairs_threshold=per_call_threshold,
        max_pairwise_comparisons=global_cap,
        correlation_id=correlation_id,
    )
    assert len(tasks_first_call) == per_call_threshold
    record_pairs(tasks_first_call)

    tasks_second_call = await pair_generation.generate_comparison_tasks(
        essays_for_comparison=essays,
        db_session=session,
        cj_batch_id=123,
        existing_pairs_threshold=per_call_threshold,
        max_pairwise_comparisons=global_cap,
        correlation_id=correlation_id,
    )
    assert len(tasks_second_call) == 1  # Only remaining global slot should be used
    record_pairs(tasks_second_call)

    tasks_third_call = await pair_generation.generate_comparison_tasks(
        essays_for_comparison=essays,
        db_session=session,
        cj_batch_id=123,
        existing_pairs_threshold=per_call_threshold,
        max_pairwise_comparisons=global_cap,
        correlation_id=correlation_id,
    )
    assert tasks_third_call == []
    assert len(existing_pairs_store) == global_cap
