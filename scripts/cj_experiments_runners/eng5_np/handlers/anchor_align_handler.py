"""ANCHOR_ALIGN_TEST mode handler for ENG5 NP runner.

Runs CJ on anchor essays only (no DB anchors) to measure prompt alignment.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
import typer
from common_core.events.cj_assessment_events import LLMConfigOverrides

from scripts.cj_experiments_runners.eng5_np.alignment_report import (
    generate_alignment_report,
)
from scripts.cj_experiments_runners.eng5_np.artefact_io import (
    load_anchor_grade_map,
    write_stub_artefact,
)
from scripts.cj_experiments_runners.eng5_np.content_upload import upload_essays_parallel
from scripts.cj_experiments_runners.eng5_np.hydrator import AssessmentRunHydrator
from scripts.cj_experiments_runners.eng5_np.inventory import build_essay_refs
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

        # Build LLMConfigOverrides with custom prompts
        llm_overrides = LLMConfigOverrides(
            system_prompt_override=system_prompt_content,
            judge_rubric_override=rubric_content,
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

        # Upload anchor essays to Content Service (treat as students)
        typer.echo(
            f"Uploading {len(anchor_files)} anchor essays to Content Service",
            err=True,
        )
        storage_id_map = asyncio.run(
            upload_essays_parallel(
                records=anchor_files,
                content_service_url=settings.content_service_url,
            )
        )

        # Build essay refs - all anchors treated as students (no is_anchor flag)
        essay_refs = build_essay_refs(
            anchors=[],  # No anchors in request - all treated as students
            students=anchor_files,
            max_comparisons=settings.max_comparisons,
            storage_id_map=storage_id_map,
        )

        # Compose request with assignment_id=None to trigger "GUEST" behavior
        original_assignment_id = settings.assignment_id
        settings.assignment_id = None  # type: ignore[assignment]

        envelope = compose_cj_assessment_request(
            settings=settings,
            essay_refs=essay_refs,
            prompt_reference=None,  # No student prompt for anchor-align-test
        )

        # Restore assignment_id for logging
        settings.assignment_id = original_assignment_id

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
            anchor_grade_map = load_anchor_grade_map(inventory.anchors_csv)
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
