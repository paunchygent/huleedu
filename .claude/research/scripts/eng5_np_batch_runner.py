"""ENG5 NP batch runner tooling.

CLI entry-point (`pdm run eng5-np-run`) modes:

* `plan` – inventory ENG5 assets and validate schema availability.
* `dry-run` – emit deterministic artefact stubs for contract tests.
* `execute` – build + publish `ELS_CJAssessmentRequestV1`, then (optionally)
  capture comparison callbacks and completion/rich result events to hydrate the
  ENG5 assessment artefact (`assessment_run.execute.json`).

Behaviour highlights:
* Deterministic file discovery + schema validation per Phase 3.3 plan.
* Async Kafka publisher plus scoped consumer that listens to
  `huleedu.llm_provider.comparison_result.v1`,
  `huleedu.cj_assessment.completed.v1`, and
  `huleedu.assessment.result.published.v1` to persist raw events and populate
  `llm_comparisons`, `bt_summary`, `grade_projections`, and `costs` in the
  artefact.
* Validation manifest + checksum recomputed as new events arrive (guards
  reproducibility requirements).
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import datetime as dt
import json
import re
import subprocess
import sys
import uuid
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, List, Sequence

import typer

from common_core.domain_enums import ContentType, CourseCode, Language
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.cj_assessment_events import (
    AssessmentResultV1,
    CJAssessmentCompletedV1,
    ELS_CJAssessmentRequestV1,
    LLMConfigOverrides,
)
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import LLMComparisonResultV1
from common_core.metadata_models import (
    EssayProcessingInputRefV1,
    StorageReferenceMetadata,
    SystemProcessingMetadata,
)
from common_core.status_enums import ProcessingStage
from huleedu_service_libs.kafka_client import KafkaBus
import os


APP = typer.Typer(help="ENG5 NP batch runner tooling (plan, dry-run, execute)")


class RunnerMode(str, Enum):
    """CLI operating modes."""

    PLAN = "plan"
    DRY_RUN = "dry-run"
    EXECUTE = "execute"


@dataclasses.dataclass(frozen=True)
class RunnerPaths:
    """Concrete filesystem locations for ENG5 NP source assets."""

    repo_root: Path
    role_models_root: Path
    instructions_path: Path
    prompt_path: Path
    anchors_csv: Path
    anchors_xlsx: Path
    anchor_docs_dir: Path
    student_docs_dir: Path
    schema_path: Path
    artefact_output_dir: Path

    @classmethod
    def from_repo_root(cls, repo_root: Path) -> "RunnerPaths":
        role_models_root = repo_root / "test_uploads" / "ANCHOR ESSAYS" / "ROLE_MODELS_ENG5_NP_2016"
        return cls(
            repo_root=repo_root,
            role_models_root=role_models_root,
            instructions_path=role_models_root / "eng5_np_vt_2017_essay_instruction.md",
            prompt_path=role_models_root / "llm_prompt_cj_assessment_eng5.md",
            anchors_csv=role_models_root / "ANCHOR_ESSAYS_BAYESIAN_INFERENCE_DATA.csv",
            anchors_xlsx=role_models_root / "ANCHOR_ESSAYS_BAYESIAN_INFERENCE_DATA.xlsx",
            anchor_docs_dir=role_models_root / "anchor_essays",
            student_docs_dir=role_models_root / "student_essays",
            schema_path=repo_root
            / "Documentation"
            / "schemas"
            / "eng5_np"
            / "assessment_run.schema.json",
            artefact_output_dir=repo_root / ".claude" / "research" / "data" / "eng5_np_2016",
        )


@dataclasses.dataclass(frozen=True)
class FileRecord:
    """Metadata about a single file on disk."""

    path: Path
    exists: bool
    size_bytes: int | None = None
    checksum: str | None = None

    @classmethod
    def from_path(cls, path: Path, compute_checksum: bool = True) -> "FileRecord":
        if not path.exists():
            return cls(path=path, exists=False)
        if path.is_file():
            size = path.stat().st_size
            checksum = sha256_of_file(path) if compute_checksum else None
            return cls(path=path, exists=True, size_bytes=size, checksum=checksum)
        return cls(path=path, exists=True)


@dataclasses.dataclass(frozen=True)
class DirectorySnapshot:
    """Summary of files discovered under a directory."""

    root: Path
    files: Sequence[FileRecord]

    @property
    def count(self) -> int:
        return len(self.files)

    @property
    def missing(self) -> bool:
        return not self.root.exists()


@dataclasses.dataclass(frozen=True)
class RunnerInventory:
    instructions: FileRecord
    prompt: FileRecord
    anchors_csv: FileRecord
    anchors_xlsx: FileRecord
    anchor_docs: DirectorySnapshot
    student_docs: DirectorySnapshot


def sha256_of_file(path: Path, chunk_size: int = 65536) -> str:
    """Return the lowercase SHA256 checksum for *path*."""

    digest = sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_directory(path: Path, patterns: Iterable[str]) -> DirectorySnapshot:
    """Return metadata for files under *path* matching *patterns*."""

    files: List[FileRecord] = []
    if path.exists():
        for pattern in patterns:
            for entry in sorted(path.glob(pattern)):
                if entry.is_file():
                    files.append(FileRecord.from_path(entry))
    return DirectorySnapshot(root=path, files=files)


def collect_inventory(paths: RunnerPaths) -> RunnerInventory:
    """Build the current ENG5 NP asset inventory."""

    anchor_patterns = ("*.docx", "*.pdf", "*.txt")
    student_patterns = ("*.docx", "*.pdf")
    return RunnerInventory(
        instructions=FileRecord.from_path(paths.instructions_path),
        prompt=FileRecord.from_path(paths.prompt_path),
        anchors_csv=FileRecord.from_path(paths.anchors_csv),
        anchors_xlsx=FileRecord.from_path(paths.anchors_xlsx),
        anchor_docs=snapshot_directory(paths.anchor_docs_dir, anchor_patterns),
        student_docs=snapshot_directory(paths.student_docs_dir, student_patterns),
    )


def ensure_execute_requirements(inventory: RunnerInventory) -> None:
    """Raise if critical ENG5 artefacts are missing for execute mode."""

    missing: list[str] = []
    if not inventory.instructions.exists:
        missing.append(f"Missing instructions: {inventory.instructions.path}")
    if not inventory.prompt.exists:
        missing.append(f"Missing prompt reference: {inventory.prompt.path}")
    if inventory.student_docs.count == 0:
        missing.append(
            f"No student essays found in {inventory.student_docs.root}. Add files before execute."
        )
    if missing:
        joined = "\n - ".join(missing)
        raise FileNotFoundError(f"Execute mode prerequisites not met:\n - {joined}")


def sanitize_identifier(value: str) -> str:
    """Convert filenames into deterministic uppercase identifiers."""

    token = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return token.upper() or "ESSAY"


def build_essay_refs(
    *,
    anchors: Sequence[FileRecord],
    students: Sequence[FileRecord],
) -> list[EssayProcessingInputRefV1]:
    """Create essay refs combining anchor and student files."""

    refs: list[EssayProcessingInputRefV1] = []
    refs.extend(_records_to_refs(anchors, prefix="anchor"))
    refs.extend(_records_to_refs(students, prefix="student"))
    return refs


def _records_to_refs(records: Sequence[FileRecord], prefix: str) -> list[EssayProcessingInputRefV1]:
    refs: list[EssayProcessingInputRefV1] = []
    for record in records:
        if not record.exists or record.path is None:
            continue
        essay_id = sanitize_identifier(record.path.stem)
        checksum = record.checksum or sha256_of_file(record.path)
        text_storage_id = f"{prefix}::{checksum}"
        refs.append(
            EssayProcessingInputRefV1(
                essay_id=essay_id,
                text_storage_id=text_storage_id,
            )
        )
    return refs


def build_prompt_reference(record: FileRecord) -> StorageReferenceMetadata | None:
    """Build a StorageReferenceMetadata entry for the student prompt."""

    if not record.exists or record.path is None:
        return None
    reference = StorageReferenceMetadata()
    storage_id = f"prompt::{record.checksum or sha256_of_file(record.path)}"
    reference.add_reference(
        ContentType.STUDENT_PROMPT_TEXT,
        storage_id=storage_id,
        path_hint=str(record.path),
    )
    return reference


def print_inventory(inventory: RunnerInventory) -> None:
    """Emit a human-readable summary for plan mode."""

    typer.echo("\nENG5 NP Asset Inventory\n========================")
    _print_file("Instructions", inventory.instructions)
    _print_file("Prompt", inventory.prompt)
    _print_file("Anchors CSV", inventory.anchors_csv)
    _print_file("Anchors XLSX", inventory.anchors_xlsx)
    _print_snapshot("Anchor essays", inventory.anchor_docs)
    _print_snapshot("Student essays", inventory.student_docs)


def _print_file(label: str, record: FileRecord) -> None:
    exists_marker = "✅" if record.exists else "❌"
    size_info = f" ({record.size_bytes:,} bytes)" if record.size_bytes is not None else ""
    typer.echo(f"{exists_marker} {label}: {record.path}{size_info}")


def _print_snapshot(label: str, snapshot: DirectorySnapshot) -> None:
    if snapshot.missing:
        typer.echo(f"❌ {label}: missing -> {snapshot.root}")
        return
    typer.echo(f"✅ {label}: {snapshot.count} files under {snapshot.root}")


def ensure_schema_available(schema_path: Path) -> dict:
    """Load and return the ENG5 schema JSON, raising if missing."""

    if not schema_path.exists():
        raise FileNotFoundError(
            f"ENG5 schema missing at {schema_path}. Did you move Documentation/schemas?"
        )
    return json.loads(schema_path.read_text(encoding="utf-8"))


def gather_git_sha(repo_root: Path) -> str:
    """Return the current HEAD SHA (or UNKNOWN on failure)."""

    try:
        result = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError:
        return "UNKNOWN"
    return result.decode().strip()


def write_stub_artefact(
    *,
    settings: RunnerSettings,
    inventory: RunnerInventory,
    schema: dict,
) -> Path:
    """Create a schema-compliant placeholder artefact file."""

    settings.output_dir.mkdir(parents=True, exist_ok=True)
    artefact = {
        "schema_version": "1.0.0",
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
            "artefact_checksum": "TODO",
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


def _record_to_json(record: FileRecord) -> dict:
    return {
        "source_path": str(record.path),
        "checksum": record.checksum,
        "exists": record.exists,
        "size_bytes": record.size_bytes,
    }


def _build_llm_overrides(
    *,
    provider: str | None,
    model: str | None,
    temperature: float | None,
    max_tokens: int | None,
) -> LLMConfigOverrides | None:
    if not any([provider, model, temperature, max_tokens]):
        return None
    provider_value = None
    if provider:
        try:
            from common_core import LLMProviderType

            provider_value = LLMProviderType(provider.upper())
        except Exception:
            provider_value = provider  # fallback to raw string, validated downstream
    return LLMConfigOverrides(
        provider_override=provider_value,
        model_override=model,
        temperature_override=temperature,
        max_tokens_override=max_tokens,
    )


def compose_cj_assessment_request(
    *,
    settings: RunnerSettings,
    essay_refs: Sequence[EssayProcessingInputRefV1],
    prompt_reference: StorageReferenceMetadata | None,
) -> EventEnvelope[ELS_CJAssessmentRequestV1]:
    """Build the ELS → CJ request envelope for execute mode."""

    if not essay_refs:
        raise ValueError("At least one essay is required to compose CJ request")

    system_metadata = SystemProcessingMetadata(
        entity_id=settings.batch_id,
        entity_type="batch",
        parent_id=str(settings.assignment_id),
        processing_stage=ProcessingStage.PENDING,
        event=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED.value,
    )

    event_data = ELS_CJAssessmentRequestV1(
        event_name=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED,
        entity_id=settings.batch_id,
        entity_type="batch",
        parent_id=str(settings.assignment_id),
        system_metadata=system_metadata,
        essays_for_cj=list(essay_refs),
        language=settings.language.value,
        course_code=settings.course_code,
        student_prompt_ref=prompt_reference,
        llm_config_overrides=settings.llm_overrides,
        assignment_id=str(settings.assignment_id),
        user_id=settings.user_id,
        org_id=settings.org_id,
    )

    envelope = EventEnvelope[ELS_CJAssessmentRequestV1](
        event_type=topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED),
        source_service="eng5_np_batch_runner",
        correlation_id=settings.correlation_id,
        data=event_data,
        metadata={"runner_mode": settings.mode.value},
    )
    return envelope


def write_cj_request_envelope(
    *,
    envelope: EventEnvelope[ELS_CJAssessmentRequestV1],
    output_dir: Path,
) -> Path:
    """Persist the CJ request envelope for auditing and replay."""

    requests_dir = output_dir / "requests"
    requests_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = requests_dir / f"els_cj_assessment_request_{timestamp}.json"
    path.write_text(envelope.model_dump_json(indent=2), encoding="utf-8")
    return path


async def publish_envelope_to_kafka(
    *,
    envelope: EventEnvelope[ELS_CJAssessmentRequestV1],
    settings: RunnerSettings,
) -> None:
    """Publish the CJ request envelope to Kafka using KafkaBus."""

    kafka_bus = KafkaBus(
        client_id=settings.kafka_client_id,
        bootstrap_servers=settings.kafka_bootstrap,
    )
    await kafka_bus.start()
    try:
        await kafka_bus.publish(
            topic=topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED),
            envelope=envelope,
            key=envelope.data.entity_id,
        )
    finally:
        await kafka_bus.stop()


async def run_publish_and_capture(
    *,
    envelope: EventEnvelope[ELS_CJAssessmentRequestV1],
    settings: RunnerSettings,
    hydrator: AssessmentRunHydrator | None,
) -> None:
    collector: AssessmentEventCollector | None = None
    collector_task: asyncio.Task[None] | None = None

    if hydrator and settings.use_kafka and settings.await_completion:
        collector = AssessmentEventCollector(settings=settings, hydrator=hydrator)
        collector_task = asyncio.create_task(collector.consume())
        await collector.wait_until_ready()

    try:
        if settings.use_kafka:
            await publish_envelope_to_kafka(envelope=envelope, settings=settings)
            typer.echo(
                "Kafka publish succeeded -> topic "
                f"{topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED)}"
            )
        else:
            typer.echo("--no-kafka supplied; skipping publish and event capture.")

        if collector:
            await collector.wait_for_completion()

    finally:
        if collector:
            collector.request_stop()
        if collector_task:
            with contextlib.suppress(Exception):
                await collector_task


def write_completion_event(
    *,
    envelope: EventEnvelope[CJAssessmentCompletedV1],
    output_dir: Path,
) -> Path:
    completions_dir = output_dir / "events" / "completions"
    completions_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = completions_dir / f"cj_completion_{timestamp}.json"
    path.write_text(envelope.model_dump_json(indent=2), encoding="utf-8")
    return path


def write_assessment_result_event(
    *,
    envelope: EventEnvelope[AssessmentResultV1],
    output_dir: Path,
) -> Path:
    results_dir = output_dir / "events" / "assessment_results"
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = results_dir / f"assessment_result_{timestamp}.json"
    path.write_text(envelope.model_dump_json(indent=2), encoding="utf-8")
    return path


def write_llm_comparison_event(
    *,
    envelope: EventEnvelope[LLMComparisonResultV1],
    output_dir: Path,
) -> Path:
    comparisons_dir = output_dir / "events" / "comparisons"
    comparisons_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = comparisons_dir / f"llm_comparison_{timestamp}.json"
    path.write_text(envelope.model_dump_json(indent=2), encoding="utf-8")
    return path


class AssessmentRunHydrator:
    """Updates ENG5 NP artefacts with live comparison + result data."""

    def __init__(
        self,
        *,
        artefact_path: Path,
        output_dir: Path,
        grade_scale: str,
        batch_id: str,
    ) -> None:
        self.artefact_path = artefact_path
        self.output_dir = output_dir
        self.grade_scale = grade_scale
        self.batch_id = batch_id
        (self.output_dir / "events").mkdir(parents=True, exist_ok=True)

    def apply_llm_comparison(self, envelope: EventEnvelope[LLMComparisonResultV1]) -> None:
        """Persist LLM callback and append it to the artefact if it matches the batch."""

        metadata = envelope.data.request_metadata or {}
        batch_hint = metadata.get("batch_id") or metadata.get("bos_batch_id")
        if batch_hint and batch_hint != self.batch_id:
            return

        write_llm_comparison_event(envelope=envelope, output_dir=self.output_dir)

        artefact = self._load_artefact()
        record = self._build_comparison_record(artefact, envelope)
        if record is None:
            return
        artefact.setdefault("llm_comparisons", []).append(record)
        self._update_costs(artefact, envelope)
        self._write_artefact(artefact)

    def apply_assessment_result(self, envelope: EventEnvelope[AssessmentResultV1]) -> None:
        """Persist and hydrate Bradley–Terry + grade projection outputs."""

        if envelope.data.batch_id != self.batch_id:
            return

        write_assessment_result_event(envelope=envelope, output_dir=self.output_dir)

        artefact = self._load_artefact()
        artefact["bt_summary"] = self._build_bt_entries(envelope)
        artefact["grade_projections"] = self._build_grade_projections(envelope)
        self._write_artefact(artefact)

    def _load_artefact(self) -> dict[str, Any]:
        return json.loads(self.artefact_path.read_text(encoding="utf-8"))

    def _write_artefact(self, artefact: dict[str, Any]) -> None:
        manifest_entries = []
        for rel_path in sorted(self._manifest_targets()):
            abs_path = self.output_dir / rel_path
            manifest_entries.append(
                {
                    "path": rel_path,
                    "sha256": sha256_of_file(abs_path),
                    "bytes": abs_path.stat().st_size,
                }
            )

        validation_block = artefact.setdefault("validation", {})
        validation_block["manifest"] = manifest_entries
        validation_block["artefact_checksum"] = ""

        serialized = json.dumps(artefact, indent=2)
        checksum = sha256(serialized.encode("utf-8")).hexdigest()
        validation_block["artefact_checksum"] = checksum
        self.artefact_path.write_text(json.dumps(artefact, indent=2), encoding="utf-8")

    def _manifest_targets(self) -> list[str]:
        targets: list[str] = []
        for subdir in ("requests", "events"):
            base = self.output_dir / subdir
            if not base.exists():
                continue
            for path in base.rglob("*.json"):
                targets.append(str(path.relative_to(self.output_dir)))
        return targets

    def _build_comparison_record(
        self,
        artefact: dict[str, Any],
        envelope: EventEnvelope[LLMComparisonResultV1],
    ) -> dict[str, Any] | None:
        metadata = envelope.data.request_metadata or {}
        essay_a = metadata.get("essay_a_id")
        essay_b = metadata.get("essay_b_id")
        if not essay_a or not essay_b:
            typer.echo(
                "Skipping LLM comparison with missing essay metadata; "
                f"correlation={envelope.correlation_id}",
                err=True,
            )
            return None

        winner_value = (envelope.data.winner.value if envelope.data.winner else "").lower()
        if "essay a" in winner_value:
            winner_id, loser_id = essay_a, essay_b
        elif "essay b" in winner_value:
            winner_id, loser_id = essay_b, essay_a
        else:
            winner_id, loser_id = "error", essay_a

        prompt_hash = metadata.get("prompt_sha256") or sha256(
            metadata.get("prompt_text", "").encode("utf-8")
        ).hexdigest()

        sequence = len(artefact.get("llm_comparisons", [])) + 1
        record = {
            "sequence": sequence,
            "correlation_id": str(envelope.correlation_id),
            "winner_id": winner_id,
            "loser_id": loser_id,
            "prompt_hash": prompt_hash,
            "provider": envelope.data.provider.value,
            "model": envelope.data.model,
            "tokens_prompt": envelope.data.token_usage.prompt_tokens,
            "tokens_completion": envelope.data.token_usage.completion_tokens,
            "cost_usd": envelope.data.cost_estimate,
            "started_at": envelope.data.requested_at.isoformat(),
            "completed_at": envelope.data.completed_at.isoformat(),
            "status": "succeeded" if not envelope.data.is_error else "failed",
        }

        if envelope.data.is_error and envelope.data.error_detail:
            record["error_code"] = envelope.data.error_detail.error_code.value
            record["error_message"] = envelope.data.error_detail.message

        return record

    def _build_bt_entries(self, envelope: EventEnvelope[AssessmentResultV1]) -> list[dict[str, Any]]:
        comparison_count = envelope.data.assessment_metadata.get("comparison_count", 0)
        entries: list[dict[str, Any]] = []
        for essay in envelope.data.essay_results:
            entries.append(
                {
                    "essay_id": essay.essay_id,
                    "theta": essay.bt_score,
                    "standard_error": 0.0,
                    "rank": essay.rank,
                    "comparison_count": comparison_count,
                    "is_anchor": essay.is_anchor,
                    "anchor_grade": essay.letter_grade if essay.is_anchor else None,
                    "grade_projection": essay.letter_grade,
                }
            )
        return entries

    def _build_grade_projections(
        self, envelope: EventEnvelope[AssessmentResultV1]
    ) -> list[dict[str, Any]]:
        metadata = envelope.data.assessment_metadata or {}
        summary = metadata.get("grade_projection_summary", {})
        probabilities = summary.get("grade_probabilities", {})

        projections: list[dict[str, Any]] = []
        for essay in envelope.data.essay_results:
            probs = probabilities.get(essay.essay_id, {essay.letter_grade: 1.0})
            projections.append(
                {
                    "essay_id": essay.essay_id,
                    "grade_scale": self.grade_scale,
                    "grade": essay.letter_grade,
                    "probabilities": probs,
                    "primary_anchor_id": None,
                    "anchor_alignment": None,
                }
            )
        return projections

    def _update_costs(
        self,
        artefact: dict[str, Any],
        envelope: EventEnvelope[LLMComparisonResultV1],
    ) -> None:
        costs = artefact.setdefault("costs", {"total_usd": 0.0, "token_counts": []})
        costs["total_usd"] = round(costs.get("total_usd", 0.0) + envelope.data.cost_estimate, 6)
        totals = {
            (entry["provider"], entry["model"]): entry
            for entry in costs.get("token_counts", [])
        }
        key = (envelope.data.provider.value, envelope.data.model)
        entry = totals.get(key)
        if not entry:
            entry = {
                "provider": key[0],
                "model": key[1],
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "usd": 0.0,
            }
            costs["token_counts"].append(entry)
            totals[key] = entry

        entry["prompt_tokens"] += envelope.data.token_usage.prompt_tokens
        entry["completion_tokens"] += envelope.data.token_usage.completion_tokens
        entry["usd"] = round(entry["usd"] + envelope.data.cost_estimate, 6)


class AssessmentEventCollector:
    """Async Kafka consumer that captures callbacks for a single ENG5 batch."""

    def __init__(self, settings: RunnerSettings, hydrator: AssessmentRunHydrator) -> None:
        self.settings = settings
        self.hydrator = hydrator
        self._ready = asyncio.Event()
        self._done = asyncio.Event()
        self._stop = asyncio.Event()
        self._rich_observed = False
        self._completion_observed = False
        self._error: Exception | None = None

    async def consume(self) -> None:
        from aiokafka import AIOKafkaConsumer

        topics = (
            topic_name(ProcessingEvent.LLM_COMPARISON_RESULT),
            topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
            topic_name(ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED),
        )

        consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self.settings.kafka_bootstrap,
            group_id=f"{self.settings.kafka_client_id}-eng5np-{self.settings.batch_id}",
            enable_auto_commit=False,
            auto_offset_reset="latest",
            session_timeout_ms=45000,
            max_poll_records=50,
        )

        await consumer.start()
        self._ready.set()
        deadline = asyncio.get_event_loop().time() + self.settings.completion_timeout

        try:
            while not self._stop.is_set():
                if self._rich_observed:
                    break
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    typer.echo(
                        "Timed out waiting for CJ assessment results; captured partial data.",
                        err=True,
                    )
                    break

                batches = await consumer.getmany(timeout_ms=1000, max_records=50)
                if not batches:
                    continue

                commit_needed = False
                for records in batches.values():
                    for record in records:
                        handled = await self._handle_record(record)
                        commit_needed = commit_needed or handled

                if commit_needed:
                    await consumer.commit()

        except Exception as exc:  # pragma: no cover - defensive guard
            self._error = exc
            raise
        finally:
            await consumer.stop()
            self._done.set()

    async def _handle_record(self, record: Any) -> bool:
        from aiokafka.structs import ConsumerRecord

        if not isinstance(record, ConsumerRecord):
            return False

        try:
            payload = record.value.decode("utf-8") if record.value else "{}"
        except Exception:
            return False

        topic = record.topic
        if topic == topic_name(ProcessingEvent.LLM_COMPARISON_RESULT):
            envelope = EventEnvelope[LLMComparisonResultV1].model_validate_json(payload)
            metadata = envelope.data.request_metadata or {}
            batch_hint = metadata.get("batch_id") or metadata.get("bos_batch_id")
            if batch_hint and batch_hint != self.settings.batch_id:
                return False
            self.hydrator.apply_llm_comparison(envelope)
            return True

        if topic == topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED):
            envelope = EventEnvelope[CJAssessmentCompletedV1].model_validate_json(payload)
            if envelope.data.entity_id != self.settings.batch_id:
                return False
            write_completion_event(envelope=envelope, output_dir=self.settings.output_dir)
            self._completion_observed = True
            return True

        if topic == topic_name(ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED):
            envelope = EventEnvelope[AssessmentResultV1].model_validate_json(payload)
            if envelope.data.batch_id != self.settings.batch_id:
                return False
            self.hydrator.apply_assessment_result(envelope)
            self._rich_observed = True
            return True

        return False

    async def wait_until_ready(self) -> None:
        await self._ready.wait()

    async def wait_for_completion(self) -> None:
        await self._done.wait()
        if self._error:
            raise self._error

    def request_stop(self) -> None:
        self._stop.set()


@dataclasses.dataclass
class RunnerSettings:
    assignment_id: uuid.UUID
    course_id: uuid.UUID
    grade_scale: str
    mode: RunnerMode
    use_kafka: bool
    output_dir: Path
    runner_version: str
    git_sha: str
    batch_id: str
    user_id: str
    org_id: str | None
    course_code: CourseCode
    language: Language
    correlation_id: uuid.UUID
    kafka_bootstrap: str
    kafka_client_id: str
    llm_overrides: LLMConfigOverrides | None
    await_completion: bool
    completion_timeout: float


def repo_root_from_this_file() -> Path:
    """Resolve the repository root relative to this script."""

    return Path(__file__).resolve().parents[3]


def main(
    mode: RunnerMode = typer.Option(RunnerMode.PLAN, "--mode", case_sensitive=False),
    assignment_id: uuid.UUID = typer.Option(
        uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "--assignment-id",
        help="Assignment ID for metadata (defaults to ENG5 placeholder)",
    ),
    course_id: uuid.UUID = typer.Option(
        uuid.UUID("22222222-2222-2222-2222-222222222222"),
        "--course-id",
        help="Course ID for metadata (defaults to ENG5 placeholder)",
    ),
    grade_scale: str = typer.Option(
        "eng5_np_legacy_9_step",
        "--grade-scale",
        help="Grade scale key registered in the CJ service",
    ),
    batch_id: str = typer.Option(
        "eng5-np-local-batch",
        "--batch-id",
        help="Logical batch identifier propagated to CJ",
    ),
    user_id: str = typer.Option(
        "eng5_np_research_runner",
        "--user-id",
        help="User ID to include in CJ request",
    ),
    org_id: str | None = typer.Option(
        None,
        "--org-id",
        help="Optional organization identifier",
    ),
    course_code: CourseCode = typer.Option(  # type: ignore[arg-type]
        CourseCode.ENG5,
        "--course-code",
        case_sensitive=False,
        help="Course code for CJ request",
    ),
    language: Language = typer.Option(  # type: ignore[arg-type]
        Language.ENGLISH,
        "--language",
        case_sensitive=False,
        help="Essay language (defaults to ENG5 English)",
    ),
    no_kafka: bool = typer.Option(
        False,
        "--no-kafka",
        help="Skip Kafka submission even in execute mode",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        help="Optional override for artefact output directory",
    ),
    kafka_bootstrap: str = typer.Option(
        os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        "--kafka-bootstrap",
        help="Kafka bootstrap servers (host:port, comma separated)",
    ),
    kafka_client_id: str = typer.Option(
        "eng5-np-runner",
        "--kafka-client-id",
        help="Kafka client_id to use when publishing",
    ),
    llm_provider: str | None = typer.Option(
        None,
        "--llm-provider",
        help="Override LLM provider (e.g., openai, anthropic)",
    ),
    llm_model: str | None = typer.Option(
        None,
        "--llm-model",
        help="Override LLM model identifier",
    ),
    llm_temperature: float | None = typer.Option(
        None,
        "--llm-temperature",
        min=0.0,
        max=2.0,
        help="Override temperature (0.0-2.0)",
    ),
    llm_max_tokens: int | None = typer.Option(
        None,
        "--llm-max-tokens",
        min=1,
        help="Override max completion tokens",
    ),
    await_completion: bool = typer.Option(
        False,
        "--await-completion/--no-await-completion",
        help="Wait for CJ completion event before exiting",
    ),
    completion_timeout: float = typer.Option(
        1800.0,
        "--completion-timeout",
        help="Timeout (seconds) when waiting for completion events",
    ),
) -> None:
    """CLI entry point orchestrating the runner modes."""

    repo_root = repo_root_from_this_file()
    paths = RunnerPaths.from_repo_root(repo_root)
    inventory = collect_inventory(paths)

    if mode is RunnerMode.PLAN:
        print_inventory(inventory)
        return

    schema = ensure_schema_available(paths.schema_path)

    settings = RunnerSettings(
        assignment_id=assignment_id,
        course_id=course_id,
        grade_scale=grade_scale,
        mode=mode,
        use_kafka=not no_kafka,
        output_dir=output_dir or paths.artefact_output_dir,
        runner_version="0.1.0",
        git_sha=gather_git_sha(repo_root),
        batch_id=batch_id,
        user_id=user_id,
        org_id=org_id,
        course_code=course_code,
        language=language,
        correlation_id=uuid.uuid4(),
        kafka_bootstrap=kafka_bootstrap,
        kafka_client_id=kafka_client_id,
        llm_overrides=_build_llm_overrides(
            provider=llm_provider,
            model=llm_model,
            temperature=llm_temperature,
            max_tokens=llm_max_tokens,
        ),
        await_completion=await_completion,
        completion_timeout=completion_timeout,
    )

    artefact_path = write_stub_artefact(settings=settings, inventory=inventory, schema=schema)
    hydrator_for_capture: AssessmentRunHydrator | None = None
    if settings.await_completion and settings.use_kafka:
        hydrator_for_capture = AssessmentRunHydrator(
            artefact_path=artefact_path,
            output_dir=settings.output_dir,
            grade_scale=settings.grade_scale,
            batch_id=settings.batch_id,
        )

    if mode is RunnerMode.EXECUTE:
        ensure_execute_requirements(inventory)
        essay_refs = build_essay_refs(
            anchors=inventory.anchor_docs.files,
            students=inventory.student_docs.files,
        )
        prompt_ref = build_prompt_reference(inventory.prompt)
        envelope = compose_cj_assessment_request(
            settings=settings,
            essay_refs=essay_refs,
            prompt_reference=prompt_ref,
        )
        request_path = write_cj_request_envelope(
            envelope=envelope,
            output_dir=settings.output_dir,
        )
        typer.echo(f"CJ request envelope written to {request_path}")
        if settings.await_completion and not settings.use_kafka:
            typer.echo("--await-completion ignored because Kafka publishing is disabled.", err=True)

        try:
            if settings.await_completion and settings.use_kafka:
                asyncio.run(
                    run_publish_and_capture(
                        envelope=envelope,
                        settings=settings,
                        hydrator=hydrator_for_capture,
                    )
                )
            elif settings.use_kafka:
                asyncio.run(publish_envelope_to_kafka(envelope=envelope, settings=settings))
                typer.echo(
                    "Kafka publish succeeded -> topic "
                    f"{topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED)}"
                )
            else:
                typer.echo("Kafka disabled; request not published.")
        except Exception as exc:  # pragma: no cover - best-effort side effect
            typer.echo(
                f"Kafka publish failed ({exc.__class__.__name__}: {exc}). "
                "Use --no-kafka to skip publishing.",
                err=True,
            )
            raise


APP.command()(main)


if __name__ == "__main__":
    APP()
