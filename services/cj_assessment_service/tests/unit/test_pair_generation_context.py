"""Tests for assessment context fetching in pair generation logic."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

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
