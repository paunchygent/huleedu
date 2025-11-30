"""Unit tests for comparison record building in AssessmentRunHydrator."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import LLMComparisonResultV1

from scripts.cj_experiments_runners.eng5_np.hydrator import AssessmentRunHydrator


def _build_envelope(
    *,
    winner: Any,
    essay_a_id: str = "essay_a",
    essay_b_id: str = "essay_b",
    is_error: bool = False,
) -> EventEnvelope[LLMComparisonResultV1]:
    now = datetime.now(timezone.utc)
    data = LLMComparisonResultV1(
        request_id="req-1",
        correlation_id="00000000-0000-0000-0000-000000000000",
        winner=winner,
        justification="Test justification",
        confidence=3.5,
        error_detail=None,
        provider="anthropic",
        model="test-model",
        response_time_ms=100,
        token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        cost_estimate=0.0,
        requested_at=now,
        completed_at=now,
        trace_id=None,
        request_metadata={
            "essay_a_id": essay_a_id,
            "essay_b_id": essay_b_id,
            "prompt_sha256": "0" * 64,
            "bos_batch_id": "batch-uuid",
        },
        is_error=is_error,
    )
    return EventEnvelope[LLMComparisonResultV1](
        event_id="00000000-0000-0000-0000-000000000001",
        event_type="LLMComparisonResultV1",
        event_timestamp=now,
        source_service="llm_provider_service",
        schema_version=1,
        correlation_id="00000000-0000-0000-0000-000000000000",
        data_schema_uri=None,
        data=data,
        metadata=None,
    )


def test_build_comparison_record_interprets_winner_essay_a(tmp_path: Path) -> None:
    hydrator = AssessmentRunHydrator(
        artefact_path=tmp_path / "artefact.json",
        output_dir=tmp_path,
        grade_scale="eng5",
        batch_id="batch",
        batch_uuid="batch-uuid",
    )
    # Seed minimal artefact
    hydrator._write_artefact({"llm_comparisons": []})  # type: ignore[arg-type]

    # Winner as "Essay A" string should map to essay_a_id
    envelope = _build_envelope(winner="Essay A", essay_a_id="A1", essay_b_id="B1")
    record = hydrator._build_comparison_record(hydrator.get_run_artefact(), envelope)

    assert record["winner_id"] == "A1"
    assert record["loser_id"] == "B1"
    assert record["confidence"] == 3.5
    assert record["justification"] == "Test justification"


def test_build_comparison_record_interprets_winner_essay_b(tmp_path: Path) -> None:
    hydrator = AssessmentRunHydrator(
        artefact_path=tmp_path / "artefact.json",
        output_dir=tmp_path,
        grade_scale="eng5",
        batch_id="batch",
        batch_uuid="batch-uuid",
    )
    hydrator._write_artefact({"llm_comparisons": []})  # type: ignore[arg-type]

    envelope = _build_envelope(winner="Essay B", essay_a_id="A1", essay_b_id="B1")
    record = hydrator._build_comparison_record(hydrator.get_run_artefact(), envelope)

    assert record["winner_id"] == "B1"
    assert record["loser_id"] == "A1"
    assert record["confidence"] == 3.5
    assert record["justification"] == "Test justification"
