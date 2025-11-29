"""EXECUTE mode handler for ENG5 NP runner.

Full execution: anchor registration, essay upload, Kafka publishing.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import aiohttp
import structlog
import typer
from common_core.event_enums import ProcessingEvent, topic_name

from scripts.cj_experiments_runners.eng5_np.artefact_io import write_stub_artefact
from scripts.cj_experiments_runners.eng5_np.cj_client import (
    AnchorRegistrationError,
    register_anchor_essays,
)
from scripts.cj_experiments_runners.eng5_np.content_upload import (
    upload_essay_content,
    upload_essays_parallel,
)
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
    - Registers anchor essays with CJ service
    - Uploads student essays to Content Service
    - Composes and publishes CJ assessment request
    - Optionally waits for completion and captures results
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
        ensure_execute_requirements(inventory)

        anchors_for_registration = list(inventory.anchor_docs.files)
        students_for_upload = list(inventory.student_docs.files)

        self._validate_execute_requirements(settings, anchors_for_registration, students_for_upload)

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

        # Register anchors with CJ service
        registration_results = self._register_anchors(
            anchors=anchors_for_registration,
            settings=settings,
        )

        logger.info(
            "anchor_registration_succeeded",
            registered=len(registration_results),
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

        # Upload prompt if exists
        prompt_storage_id = self._upload_prompt(inventory, settings)

        # Compose and write request
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

        return 0

    def _validate_execute_requirements(
        self,
        settings: RunnerSettings,
        anchors: list,
        students: list,
    ) -> None:
        """Validate all requirements for EXECUTE mode.

        Raises:
            RuntimeError: If requirements not met
        """
        if not anchors:
            raise RuntimeError(
                "Anchor essays are required for ENG5 execute runs; populate anchors directory."
            )
        if not settings.cj_service_url:
            raise RuntimeError(
                "CJ service URL is required to register anchors in EXECUTE mode. "
                "Set --cj-service-url or CJ_SERVICE_URL env var."
            )
        if not students:
            raise RuntimeError("No essays available for upload; ensure dataset is populated")

    def _register_anchors(
        self,
        anchors: list,
        settings: RunnerSettings,
    ) -> list:
        """Register anchor essays with CJ service.

        Returns:
            Registration results

        Raises:
            RuntimeError: If registration fails
        """
        try:
            registration_results = asyncio.run(
                register_anchor_essays(
                    anchors=anchors,
                    assignment_id=settings.assignment_id,
                    cj_service_url=settings.cj_service_url,
                )
            )
        except AnchorRegistrationError as exc:
            logger.error("anchor_registration_failed", error=str(exc))
            raise RuntimeError(
                "Anchor registration failed; aborting EXECUTE run so CJ only uses DB-owned anchors."
            ) from exc

        if not registration_results:
            raise RuntimeError("Anchor registration returned no results; aborting EXECUTE run.")

        typer.echo(
            f"Registered {len(registration_results)} anchors via CJ service",
            err=True,
        )
        return registration_results

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
