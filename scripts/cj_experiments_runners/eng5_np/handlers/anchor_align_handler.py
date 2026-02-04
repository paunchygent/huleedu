"""ANCHOR_ALIGN_TEST mode handler for the ENG5 NP runner.

Purpose:
    Run CJ on anchor essays only (treated as students) to measure prompt/rubric alignment against
    expert anchor grades without relying on DB-owned anchors or grade projection.

Relationships:
    - Uses GUEST semantics (`assignment_id=None`) when composing the CJ request.
    - Uses `upload_cache` to reuse Content Service `storage_id` results across repeated prompt
      experiments.
    - Generates a markdown alignment report via `alignment_report.generate_alignment_report`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
import typer
from common_core.events.cj_assessment_events import LLMConfigOverrides

from scripts.cj_experiments_runners.eng5_np.alignment_report import (
    generate_alignment_report,
)
from scripts.cj_experiments_runners.eng5_np.anchor_utils import extract_grade_from_filename
from scripts.cj_experiments_runners.eng5_np.artefact_io import (
    load_anchor_grade_map,
    load_anchor_id_lookup,
    write_stub_artefact,
)
from scripts.cj_experiments_runners.eng5_np.content_upload import upload_essays_parallel
from scripts.cj_experiments_runners.eng5_np.hydrator import AssessmentRunHydrator
from scripts.cj_experiments_runners.eng5_np.inventory import (
    FileRecord,
    build_essay_refs,
)
from scripts.cj_experiments_runners.eng5_np.kafka_flow import (
    publish_envelope_to_kafka,
    run_publish_and_capture,
)
from scripts.cj_experiments_runners.eng5_np.logging_support import (
    load_artefact_data,
    log_validation_state,
)
from scripts.cj_experiments_runners.eng5_np.requests import (
    compose_cj_assessment_request,
    write_cj_request_envelope,
)
from scripts.cj_experiments_runners.eng5_np.schema import ensure_schema_available
from scripts.cj_experiments_runners.eng5_np.upload_cache import (
    default_cache_path,
    upload_records_with_cache,
)
from scripts.cj_experiments_runners.eng5_np.utils import make_anchor_key

if TYPE_CHECKING:
    from scripts.cj_experiments_runners.eng5_np.inventory import RunnerInventory
    from scripts.cj_experiments_runners.eng5_np.paths import RunnerPaths
    from scripts.cj_experiments_runners.eng5_np.settings import RunnerSettings


logger = structlog.get_logger(__name__)


def _load_prompt_file(path: Path | None, label: str) -> str | None:
    """Load prompt content from file with validation.

    Args:
        path: Path to the prompt file (may be None)
        label: Human-readable label for error messages

    Returns:
        File content as string, or None if path is None

    Raises:
        typer.BadParameter: If file does not exist or is empty
    """
    if path is None:
        return None
    if not path.exists():
        raise typer.BadParameter(f"{label} file not found: {path}")
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise typer.BadParameter(f"{label} file is empty: {path}")
    typer.echo(f"Loaded {label}: {path} ({len(content)} chars)", err=True)
    return content


class AnchorAlignHandler:
    """Handler for ANCHOR_ALIGN_TEST mode.

    Runs CJ assessment on anchor essays only, treating them as student essays.
    Uses assignment_id=None to trigger GUEST behavior (no DB anchors, no grade projection).
    Generates alignment report comparing BT ranks to expert grades.
    """

    def execute(
        self,
        settings: RunnerSettings,
        inventory: RunnerInventory,
        paths: RunnerPaths,
    ) -> int:
        """Execute ANCHOR_ALIGN_TEST mode logic.

        Args:
            settings: Runner configuration
            inventory: File inventory (anchors, students, prompt)
            paths: Path configuration

        Returns:
            Exit code (0 for success)
        """
        anchor_files = list(inventory.anchor_docs.files)
        if not anchor_files:
            raise RuntimeError(
                "Anchor essays are required for anchor-align-test mode; populate anchors directory."
            )

        typer.echo(
            f"ANCHOR_ALIGN_TEST: {len(anchor_files)} anchors compared as student essays",
            err=True,
        )

        # Load custom prompts if provided
        rubric_content = _load_prompt_file(settings.rubric_file, "judge rubric")
        system_prompt_content = _load_prompt_file(settings.system_prompt_file, "system prompt")

        # Update settings with loaded prompt text
        settings.rubric_text = rubric_content
        settings.system_prompt_text = system_prompt_content

        # Build LLMConfigOverrides with custom prompts, preserving any
        # provider/model overrides that were already configured via the CLI.
        existing_overrides = settings.llm_overrides
        llm_overrides = LLMConfigOverrides(
            provider_override=getattr(existing_overrides, "provider_override", None),
            model_override=getattr(existing_overrides, "model_override", None),
            temperature_override=getattr(existing_overrides, "temperature_override", None),
            max_tokens_override=getattr(existing_overrides, "max_tokens_override", None),
            system_prompt_override=system_prompt_content,
            judge_rubric_override=rubric_content,
            reasoning_effort=getattr(existing_overrides, "reasoning_effort", None),
            output_verbosity=getattr(existing_overrides, "output_verbosity", None),
        )
        settings.llm_overrides = llm_overrides

        # Create stub artefact and hydrator
        schema = ensure_schema_available(paths.schema_path)
        artefact_path = write_stub_artefact(
            settings=settings,
            inventory=inventory,
            schema=schema,
        )

        hydrator: AssessmentRunHydrator | None = None
        if settings.await_completion and settings.use_kafka:
            hydrator = AssessmentRunHydrator(
                artefact_path=artefact_path,
                output_dir=settings.output_dir,
                grade_scale=settings.grade_scale,
                batch_id=settings.batch_id,
                batch_uuid=settings.batch_uuid,
            )

        # Build mapping from anchor file name to normalized anchor ID for essay IDs
        anchor_id_lookup = load_anchor_id_lookup(inventory.anchors_csv)

        # Upload anchor essays to Content Service (treat as students), with disk cache.
        cache_path = default_cache_path(output_dir=settings.output_dir)

        def _uploader(records: Sequence[FileRecord], url: str) -> dict[str, str]:
            return asyncio.run(upload_essays_parallel(records=records, content_service_url=url))

        storage_id_map, outcome = upload_records_with_cache(
            records=anchor_files,
            content_service_url=settings.content_service_url,
            cache_path=cache_path,
            force_reupload=settings.force_reupload,
            uploader=_uploader,
        )
        if outcome.cache_ignored_reason:
            typer.echo(
                f"⚠️  Upload cache ignored ({outcome.cache_ignored_reason}); starting fresh.",
                err=True,
            )
        typer.echo(
            "Content upload cache: "
            f"reused={outcome.reused_count} uploaded={outcome.uploaded_count} "
            f"path={outcome.cache_path}",
            err=True,
        )

        # Build essay refs - all anchors treated as students (no is_anchor flag)
        def _anchor_align_student_id_factory(record: FileRecord) -> str:
            """Generate essay_id for anchor-align-test student records.

            Uses the normalized anchor ID from the grade CSV when available and
            falls back to a generic anchor key derived from the filename.
            IDs are prefixed with ``student::`` so CJ treats them as students
            (not DB anchors) while still fitting within the 36-char limit.
            """
            raw_anchor_id = anchor_id_lookup.get(record.path.name) or record.path.stem
            anchor_key = make_anchor_key(raw_anchor_id)
            essay_id = f"student::{anchor_key}"
            # Safety guard to respect CJ els_essay_id String(36) limit
            if len(essay_id) > 36:  # pragma: no cover - defensive guard
                # Fall back to a truncated deterministic ID while preserving prefix
                from scripts.cj_experiments_runners.eng5_np.utils import generate_essay_id

                suffix = generate_essay_id(anchor_key, max_length=36 - len("student::"))
                essay_id = f"student::{suffix}"
            return essay_id

        essay_refs = build_essay_refs(
            anchors=[],  # No anchors in request - all treated as students
            students=anchor_files,
            max_comparisons=settings.max_comparisons,
            storage_id_map=storage_id_map,
            student_id_factory=_anchor_align_student_id_factory,
        )

        # Compose request with assignment_id=None to trigger "GUEST" behavior
        original_cj_assignment_id = settings.cj_assignment_id
        settings.cj_assignment_id = None

        envelope = compose_cj_assessment_request(
            settings=settings,
            essay_refs=essay_refs,
            prompt_reference=None,  # No student prompt for anchor-align-test
        )

        # Restore assignment_id for logging
        settings.cj_assignment_id = original_cj_assignment_id

        request_path = write_cj_request_envelope(
            envelope=envelope,
            output_dir=settings.output_dir,
        )
        typer.echo(f"CJ request envelope written to {request_path}")

        if settings.use_kafka:
            self._publish_and_report(
                settings=settings,
                inventory=inventory,
                envelope=envelope,
                hydrator=hydrator,
                system_prompt_content=system_prompt_content,
                rubric_content=rubric_content,
                anchor_count=len(anchor_files),
            )
        else:
            typer.echo("Kafka disabled; request not published.")

        log_validation_state(
            logger=logger,
            artefact_path=artefact_path,
            artefact_data=load_artefact_data(artefact_path),
        )

        return 0

    def _publish_and_report(
        self,
        settings: RunnerSettings,
        inventory: RunnerInventory,
        envelope: dict,
        hydrator: AssessmentRunHydrator | None,
        system_prompt_content: str | None,
        rubric_content: str | None,
        anchor_count: int,
    ) -> None:
        """Publish to Kafka and generate alignment report if awaiting completion.

        Args:
            settings: Runner configuration
            inventory: File inventory
            envelope: CJ request envelope
            hydrator: Result hydrator (or None)
            system_prompt_content: System prompt used
            rubric_content: Rubric used
            anchor_count: Number of anchors
        """
        if settings.await_completion:
            asyncio.run(
                run_publish_and_capture(
                    envelope=envelope,
                    settings=settings,
                    hydrator=hydrator,
                )
            )

            # Generate alignment report
            # Prefer explicit grade map from anchors CSV when provided.
            anchor_grade_map = load_anchor_grade_map(inventory.anchors_csv)

            # Fallback: derive expert grades directly from anchor filenames when
            # the CSV does not describe the current anchors (ENG5 vt_2017 set).
            if not anchor_grade_map:
                local_anchor_id_lookup = load_anchor_id_lookup(inventory.anchors_csv)
                derived_map: dict[str, str] = {}
                for record in inventory.anchor_docs.files:
                    if not record.exists:
                        continue
                    raw_anchor_id = local_anchor_id_lookup.get(record.path.name) or record.path.stem
                    anchor_key = make_anchor_key(raw_anchor_id)
                    grade = extract_grade_from_filename(record.path.name)
                    derived_map[anchor_key] = grade
                anchor_grade_map = derived_map

            report_path = generate_alignment_report(
                hydrator=hydrator,
                anchor_grade_map=anchor_grade_map,
                system_prompt_text=system_prompt_content,
                rubric_text=rubric_content,
                batch_id=settings.batch_id,
                output_dir=settings.output_dir,
            )
            typer.echo(f"Alignment report written to {report_path}")
            logger.info(
                "anchor_align_test_complete",
                report_path=str(report_path),
                anchor_count=anchor_count,
            )
        else:
            asyncio.run(publish_envelope_to_kafka(envelope=envelope, settings=settings))
            typer.echo(
                "Kafka publish succeeded. Use --await-completion to generate alignment report."
            )
