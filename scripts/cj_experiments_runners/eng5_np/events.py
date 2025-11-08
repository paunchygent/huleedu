"""Event persistence helpers for ENG5 NP runner."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from common_core.events.cj_assessment_events import (
    AssessmentResultV1,
    CJAssessmentCompletedV1,
)
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import LLMComparisonResultV1


def _timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")


def write_completion_event(
    *,
    envelope: EventEnvelope[CJAssessmentCompletedV1],
    output_dir: Path,
) -> Path:
    completions_dir = output_dir / "events" / "completions"
    completions_dir.mkdir(parents=True, exist_ok=True)
    path = completions_dir / f"cj_completion_{_timestamp()}.json"
    path.write_text(envelope.model_dump_json(indent=2), encoding="utf-8")
    return path


def write_assessment_result_event(
    *,
    envelope: EventEnvelope[AssessmentResultV1],
    output_dir: Path,
) -> Path:
    results_dir = output_dir / "events" / "assessment_results"
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"assessment_result_{_timestamp()}.json"
    path.write_text(envelope.model_dump_json(indent=2), encoding="utf-8")
    return path


def write_llm_comparison_event(
    *,
    envelope: EventEnvelope[LLMComparisonResultV1],
    output_dir: Path,
) -> Path:
    comparisons_dir = output_dir / "events" / "comparisons"
    comparisons_dir.mkdir(parents=True, exist_ok=True)
    path = comparisons_dir / f"llm_comparison_{_timestamp()}.json"
    path.write_text(envelope.model_dump_json(indent=2), encoding="utf-8")
    return path
