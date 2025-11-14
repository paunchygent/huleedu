"""Artefact writing helpers for ENG5 NP runner."""

from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any, Sequence

import typer

from scripts.cj_experiments_runners.eng5_np.inventory import FileRecord, RunnerInventory
from scripts.cj_experiments_runners.eng5_np.settings import RunnerSettings
from scripts.cj_experiments_runners.eng5_np.utils import sanitize_identifier, sha256_of_file

_EMPTY_HASH = "0" * 64


def write_stub_artefact(
    *,
    settings: RunnerSettings,
    inventory: RunnerInventory,
    schema: dict[str, Any],
) -> Path:
    """Create a schema-compliant placeholder artefact file."""

    settings.output_dir.mkdir(parents=True, exist_ok=True)
    runner_status = {
        "partial_data": False,
        "timeout_seconds": 0.0,
        "observed_events": {
            "llm_comparisons": 0,
            "assessment_results": 0,
            "completions": 0,
        },
    }

    grade_map = _load_anchor_grade_map(inventory.anchors_csv)
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
            "batch_uuid": str(settings.batch_uuid),
            "batch_id": settings.batch_id,
            "course_code": settings.course_code.value,
            "llm_config_overrides": settings.llm_overrides.model_dump()
            if settings.llm_overrides
            else None,
        },
        "inputs": {
            "instructions": _document_blob("Instructions", inventory.instructions),
            "prompt_reference": _document_blob("Prompt reference", inventory.prompt),
            "anchors": _build_anchor_records(inventory.anchor_docs.files, grade_map),
            "students": _build_student_records(inventory.student_docs.files),
        },
        "llm_comparisons": [],
        "bt_summary": [],
        "grade_projections": [],
        "costs": {"total_usd": 0.0, "token_counts": []},
        "validation": {
            "artefact_checksum": _EMPTY_HASH,
            "manifest": [],
            "cli_environment": {
                "python": sys.version.split()[0],
                "pdm": "unknown",
                "os": sys.platform,
                "docker_compose": "unknown",
            },
            "runner_status": runner_status,
        },
    }

    output_file = settings.output_dir / f"assessment_run.{settings.mode.value}.json"
    serialized = json.dumps(artefact, indent=2)
    artefact["validation"]["artefact_checksum"] = sha256(serialized.encode("utf-8")).hexdigest()
    output_file.write_text(json.dumps(artefact, indent=2), encoding="utf-8")
    typer.echo(f"Stub artefact written to {output_file}")
    return output_file


def _document_blob(label: str, record: FileRecord) -> dict[str, Any]:
    """Return a schema-compliant document blob, warning if files are missing."""

    if not record.exists:
        typer.echo(f"⚠️  {label} missing at {record.path}; writing placeholder blob", err=True)
        return {
            "source_path": str(record.path),
            "checksum": _EMPTY_HASH,
            "content": "",
        }

    checksum = record.checksum or sha256_of_file(record.path)
    try:
        content = record.path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        typer.echo(
            f"⚠️  {label} is not UTF-8 text ({record.path}); omitting content for artefact",
            err=True,
        )
        content = ""

    return {
        "source_path": str(record.path),
        "checksum": checksum,
        "content": content,
    }


def _build_anchor_records(
    records: Sequence[FileRecord], grade_map: dict[str, str]
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for record in records:
        if not record.exists:
            continue
        anchor_id = sanitize_identifier(record.path.stem)
        checksum = record.checksum or sha256_of_file(record.path)
        entries.append(
            {
                "anchor_id": anchor_id,
                "file_name": record.path.name,
                "grade": grade_map.get(anchor_id, "UNKNOWN"),
                "source_path": str(record.path),
                "checksum": checksum,
            }
        )
    if not entries:
        entries.append(
            {
                "anchor_id": "UNKNOWN_ANCHOR",
                "file_name": "missing",
                "grade": "UNKNOWN",
                "source_path": "",
                "checksum": _EMPTY_HASH,
            }
        )
    return entries


def _build_student_records(records: Sequence[FileRecord]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for record in records:
        if not record.exists:
            continue
        essay_id = sanitize_identifier(record.path.stem).lower()
        while len(essay_id) < 3:
            essay_id += "_"
        checksum = record.checksum or sha256_of_file(record.path)
        entries.append(
            {
                "essay_id": essay_id,
                "file_name": record.path.name,
                "source_path": str(record.path),
                "checksum": checksum,
            }
        )
    if not entries:
        entries.append(
            {
                "essay_id": "unknown_student",
                "file_name": "missing",
                "source_path": "",
                "checksum": _EMPTY_HASH,
            }
        )
    return entries


def _load_anchor_grade_map(record: FileRecord) -> dict[str, str]:
    if not record.exists:
        return {}

    grade_map: dict[str, str] = {}
    try:
        with record.path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                return {}

            lookup_fields = [
                field
                for field in reader.fieldnames
                if field.lower() in {"grade", "pred_mode_grade"}
            ]
            for row in reader:
                anchor_id = row.get("ANCHOR-ID") or row.get("anchor_id")
                if not anchor_id:
                    continue
                normalized_id = sanitize_identifier(anchor_id)
                grade = next((row.get(field) for field in lookup_fields if row.get(field)), None)
                if grade:
                    grade_map[normalized_id] = str(grade)
    except FileNotFoundError:
        return {}
    except Exception as exc:  # pragma: no cover - defensive guard
        typer.echo(f"⚠️  Failed to parse anchor grade map: {exc}", err=True)
    return grade_map
