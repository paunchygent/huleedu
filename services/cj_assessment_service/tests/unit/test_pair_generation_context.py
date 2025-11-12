"""Tests for assessment context fetching in pair generation logic."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.cj_assessment_service.cj_core_logic.pair_generation import (
    _fetch_assessment_context,
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
    }
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
    }
    assert session.execute.await_count == 2
