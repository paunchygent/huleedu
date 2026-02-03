"""EXECUTE mode handler for ENG5 NP runner.

Full execution: student essay upload, Kafka publishing, optional post-run extraction.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import aiohttp
import structlog
import typer
from common_core.event_enums import ProcessingEvent, topic_name

from scripts.cj_experiments_runners.eng5_np.artefact_io import write_stub_artefact
from scripts.cj_experiments_runners.eng5_np.content_upload import (
    upload_essay_content,
    upload_essays_parallel,
)
from scripts.cj_experiments_runners.eng5_np.eng5_db_extract import run_eng5_db_extraction
from scripts.cj_experiments_runners.eng5_np.hydrator import AssessmentRunHydrator
from scripts.cj_experiments_runners.eng5_np.inventory import (
    FileRecord,
    build_essay_refs,
    ensure_execute_requirements,
)
from scripts.cj_experiments_runners.eng5_np.kafka_flow import (
    publish_envelope_to_kafka,
    run_publish_and_capture,
)
from scripts.cj_experiments_runners.eng5_np.logging_support import (
    load_artefact_data,
    log_validation_state,
    print_batching_metrics_hints,
    print_run_summary,
)
from scripts.cj_experiments_runners.eng5_np.requests import (
    build_prompt_reference,
    compose_cj_assessment_request,
    write_cj_request_envelope,
)
from scripts.cj_experiments_runners.eng5_np.schema import ensure_schema_available

if TYPE_CHECKING:
    from scripts.cj_experiments_runners.eng5_np.inventory import RunnerInventory
    from scripts.cj_experiments_runners.eng5_np.paths import RunnerPaths
    from scripts.cj_experiments_runners.eng5_np.settings import RunnerSettings


logger = structlog.get_logger(__name__)


class ExecuteHandler:
    """Handler for EXECUTE mode.

    Full execution mode that:
    - Uploads student essays to Content Service
    - Composes and publishes CJ assessment request
    - Optionally waits for completion and captures results
    - Optionally extracts CJ DB results after completion (R5)
    """

    def execute(
        self,
        settings: RunnerSettings,
        inventory: RunnerInventory,
        paths: RunnerPaths,
    ) -> int:
        """Execute EXECUTE mode logic.

        Args:
            settings: Runner configuration
            inventory: File inventory (anchors, students, prompt)
            paths: Path configuration

        Returns:
            Exit code (0 for success)
        """
        ensure_execute_requirements(
            inventory,
            require_prompt=settings.cj_assignment_id is None,
        )

        students_for_upload = list(inventory.student_docs.files)

        if settings.cj_anchor_count is None:
            raise RuntimeError(
                "CJ anchor preflight missing (settings.cj_anchor_count is None). "
                "Run execute via the CLI so preflight is performed."
            )

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

        # Upload student essays
        storage_id_map = self._upload_essays(
            students=students_for_upload,
            settings=settings,
        )

        # Build essay refs
        essay_ref_anchors: list[FileRecord] = []
        essay_ref_students = students_for_upload

        essay_refs = build_essay_refs(
            anchors=essay_ref_anchors,
            students=essay_ref_students,
            max_comparisons=None,
            storage_id_map=storage_id_map,
        )

        # Assignment-bound runs do not upload prompts; CJ hydrates from assessment_instructions.
        prompt_ref = None
        if settings.cj_assignment_id is None:
            prompt_storage_id = self._upload_prompt(inventory, settings)
            prompt_ref = build_prompt_reference(inventory.prompt, storage_id=prompt_storage_id)

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

        # Publish and capture
        self._publish_request(
            settings=settings,
            envelope=envelope,
            hydrator=hydrator,
            artefact_path=artefact_path,
        )

        log_validation_state(
            logger=logger,
            artefact_path=artefact_path,
            artefact_data=load_artefact_data(artefact_path),
        )

        if settings.await_completion and settings.auto_extract_eng5_db:
            exit_code = self._maybe_run_db_extraction(settings=settings, hydrator=hydrator)
            if exit_code != 0:
                return exit_code

        return 0

    def _maybe_run_db_extraction(
        self,
        *,
        settings: RunnerSettings,
        hydrator: AssessmentRunHydrator | None,
    ) -> int:
        if hydrator is None:
            raise RuntimeError(
                "--auto-extract-eng5-db requires --await-completion and Kafka publishing."
            )

        runner_status = hydrator.runner_status()
        completions = int(runner_status.get("observed_events", {}).get("completions", 0))
        if completions <= 0:
            hydrator.update_post_run(
                key="eng5_db_extract",
                payload={
                    "status": "skipped",
                    "reason": "no_completion_observed",
                    "batch_uuid": str(settings.batch_uuid),
                },
            )
            typer.echo(
                "⚠️  Auto-extract skipped: no completion event observed for this batch.",
                err=True,
            )
            return 1

        started = time.monotonic()
        result = run_eng5_db_extraction(
            batch_identifier=str(settings.batch_uuid),
            output_dir=settings.output_dir / "db_extract",
            output_format="text",
        )
        elapsed = round(time.monotonic() - started, 2)

        status = "succeeded" if result.exit_code == 0 else "failed"
        hydrator.update_post_run(
            key="eng5_db_extract",
            payload={
                "status": status,
                "batch_completed": True,
                "batch_uuid": str(settings.batch_uuid),
                "output_format": result.output_format,
                "output_path": str(result.output_path),
                "exit_code": result.exit_code,
                "duration_seconds": elapsed,
                "error": result.error,
            },
        )

        if result.exit_code != 0:
            typer.echo(
                "❌ CJ batch completed, but ENG5 DB extraction failed "
                f"(exit_code={result.exit_code}). Output captured at {result.output_path}",
                err=True,
            )
            return 2

        typer.echo(
            f"✅ ENG5 DB extraction captured at {result.output_path}",
            err=True,
        )
        return 0

    def _upload_essays(
        self,
        students: list,
        settings: RunnerSettings,
    ) -> dict[str, str]:
        """Upload student essays to Content Service.

        Returns:
            Mapping of checksum to storage_id
        """
        typer.echo(
            f"Uploading {len(students)} essays to Content Service at "
            f"{settings.content_service_url}",
            err=True,
        )
        return asyncio.run(
            upload_essays_parallel(
                records=students,
                content_service_url=settings.content_service_url,
            )
        )

    def _upload_prompt(
        self,
        inventory: RunnerInventory,
        settings: RunnerSettings,
    ) -> str | None:
        """Upload prompt file if it exists.

        Returns:
            Storage ID or None
        """
        if not inventory.prompt.exists:
            return None

        async def _upload() -> str:
            timeout = aiohttp.ClientTimeout(total=300)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                return await upload_essay_content(
                    inventory.prompt.path,
                    content_service_url=settings.content_service_url,
                    session=session,
                )

        prompt_storage_id = asyncio.run(_upload())
        logger.info(
            "prompt_uploaded",
            storage_id=prompt_storage_id,
            path=str(inventory.prompt.path),
        )
        return prompt_storage_id

    def _publish_request(
        self,
        settings: RunnerSettings,
        envelope: dict,
        hydrator: AssessmentRunHydrator | None,
        artefact_path,
    ) -> None:
        """Publish request to Kafka and optionally capture results."""
        if settings.await_completion and not settings.use_kafka:
            typer.echo(
                "--await-completion ignored because Kafka publishing is disabled.",
                err=True,
            )
            logger.warning("await_completion_ignored", reason="no_kafka")

        if settings.use_kafka:
            try:
                if settings.await_completion:
                    asyncio.run(
                        run_publish_and_capture(
                            envelope=envelope,
                            settings=settings,
                            hydrator=hydrator,
                        )
                    )
                    summary = print_run_summary(artefact_path)
                    print_batching_metrics_hints(
                        llm_batching_mode_hint=settings.llm_batching_mode_hint,
                    )
                    logger.info(
                        "runner_execution_complete",
                        artefact_path=str(artefact_path),
                        runner_status=hydrator.runner_status() if hydrator else None,
                    )
                    log_validation_state(
                        logger=logger,
                        artefact_path=artefact_path,
                        artefact_data=summary,
                    )
                else:
                    asyncio.run(publish_envelope_to_kafka(envelope=envelope, settings=settings))
                    typer.echo(
                        "Kafka publish succeeded -> topic "
                        f"{topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED)}"
                    )
                    logger.info(
                        "runner_request_published",
                        topic=topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED),
                        await_completion=settings.await_completion,
                    )
            except Exception as exc:
                typer.echo(
                    f"Kafka publish failed ({exc.__class__.__name__}: {exc}). "
                    "Use --no-kafka to skip publishing.",
                    err=True,
                )
                logger.exception(
                    "runner_publish_failed",
                    error_type=exc.__class__.__name__,
                )
                raise
        else:
            typer.echo("Kafka disabled; request not published.")
            logger.info("runner_request_skipped", reason="no_kafka")
