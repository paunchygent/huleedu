from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.prompt_cache_benchmark.fixtures import BenchmarkFixture
from services.cj_assessment_service.models_api import EssayForComparison


def load_fixture_from_json(path: Path) -> BenchmarkFixture:
    """Load a benchmark fixture from a JSON file.

    Expected shape:
    {
      "name": "eng5",
      "assignment_id": "eng5-assignment",
      "assessment_context": {
        "student_prompt_text": "...",
        "assessment_instructions": "...",
        "judge_rubric_text": "...",
        "system_prompt": "..."          # optional
      },
      "anchors": [{"id": "...", "text": "..."}],
      "students": [{"id": "...", "text": "..."}]
    }
    """

    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))

    try:
        assessment_context = data["assessment_context"]
        anchors = data.get("anchors") or data.get("anchor_essays") or []
        students = data.get("students") or data.get("essays") or []
        assignment_id = data["assignment_id"]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Fixture missing required key: {exc}") from exc

    if not anchors or not students:
        raise ValueError("Fixture must include anchors and students/essays.")

    anchor_models = [
        EssayForComparison(id=item["id"], text_content=item["text"]) for item in anchors
    ]
    essay_models = [
        EssayForComparison(id=item["id"], text_content=item["text"]) for item in students
    ]

    name = data.get("name") or path.stem

    return BenchmarkFixture(
        name=name,
        assignment_id=assignment_id,
        assessment_context=assessment_context,
        anchors=anchor_models,
        essays=essay_models,
    )
