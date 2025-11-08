"""Artefact writing helpers for ENG5 NP runner."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import typer

from scripts.cj_experiments_runners.eng5_np.inventory import RunnerInventory
from scripts.cj_experiments_runners.eng5_np.settings import RunnerSettings


def write_stub_artefact(
    *,
    settings: RunnerSettings,
    inventory: RunnerInventory,
    schema: dict[str, Any],
) -> Path:
    """Create a schema-compliant placeholder artefact file."""

    settings.output_dir.mkdir(parents=True, exist_ok=True)
    artefact = {
        "schema_version": schema.get("schema_version", "1.0.0"),
        "metadata": {
            "assignment_id": str(settings.assignment_id),
            "course_id": str(settings.course_id),
            "grade_scale": settings.grade_scale,
            "runner_version": settings.runner_version,
            "git_sha": settings.git_sha,
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "runner_mode": settings.mode.value,
            "batch_id": settings.batch_id,
            "course_code": settings.course_code.value,
            "llm_config_overrides": settings.llm_overrides.model_dump()
            if settings.llm_overrides
            else None,
        },
        "inputs": {
            "instructions": _record_to_json(inventory.instructions),
            "prompt_reference": _record_to_json(inventory.prompt),
            "anchors": [_record_to_json(record) for record in inventory.anchor_docs.files],
            "students": [_record_to_json(record) for record in inventory.student_docs.files],
        },
        "llm_comparisons": [],
        "bt_summary": [],
        "grade_projections": [],
        "costs": {"total_usd": 0.0, "token_counts": []},
        "validation": {
            "artefact_checksum": "",
            "manifest": [],
            "cli_environment": {
                "python": sys.version.split()[0],
                "pdm": "unknown",
                "os": sys.platform,
                "docker_compose": "unknown",
            },
        },
    }

    output_file = settings.output_dir / f"assessment_run.{settings.mode.value}.json"
    output_file.write_text(json.dumps(artefact, indent=2), encoding="utf-8")
    typer.echo(f"Stub artefact written to {output_file}")
    return output_file


def _record_to_json(record: Any) -> dict[str, Any]:
    return {
        "source_path": str(record.path),
        "checksum": record.checksum,
        "exists": record.exists,
        "size_bytes": record.size_bytes,
    }
