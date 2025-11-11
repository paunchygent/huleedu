"""Typer CLI entrypoint for the ENG5 NP batch runner."""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import typer
from common_core import LLMProviderType
from common_core.domain_enums import CourseCode, Language
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.cj_assessment_events import LLMConfigOverrides

from scripts.cj_experiments_runners.eng5_np import __version__
from scripts.cj_experiments_runners.eng5_np.artefact_io import write_stub_artefact
from scripts.cj_experiments_runners.eng5_np.cj_client import (
    AnchorRegistrationError,
    register_anchor_essays,
)
from scripts.cj_experiments_runners.eng5_np.content_upload import upload_essays_parallel
from scripts.cj_experiments_runners.eng5_np.environment import (
    gather_git_sha,
    repo_root_from_package,
)
from scripts.cj_experiments_runners.eng5_np.hydrator import AssessmentRunHydrator
from scripts.cj_experiments_runners.eng5_np.inventory import (
    FileRecord,
    apply_comparison_limit,
    build_essay_refs,
    collect_inventory,
    ensure_execute_requirements,
    print_inventory,
    snapshot_directory,
)
from scripts.cj_experiments_runners.eng5_np.kafka_flow import (
    publish_envelope_to_kafka,
    run_publish_and_capture,
)
from scripts.cj_experiments_runners.eng5_np.logging_support import (
    configure_cli_logging,
    load_artefact_data,
    log_validation_state,
    print_run_summary,
    setup_cli_logger,
)
from scripts.cj_experiments_runners.eng5_np.paths import RunnerPaths
from scripts.cj_experiments_runners.eng5_np.requests import (
    build_prompt_reference,
    compose_cj_assessment_request,
    write_cj_request_envelope,
)
from scripts.cj_experiments_runners.eng5_np.schema import ensure_schema_available
from scripts.cj_experiments_runners.eng5_np.settings import RunnerMode, RunnerSettings

app = typer.Typer(help="ENG5 NP batch runner tooling (plan, dry-run, execute)")


@app.command("register-anchors")
def register_anchors_command(
    assignment_id: uuid.UUID = typer.Argument(..., help="Assignment ID to bind anchors to"),
    cj_service_url: str = typer.Option(
        os.getenv("CJ_SERVICE_URL", "http://localhost:9095"),
        help="CJ Assessment Service base URL",
    ),
    anchor_dir: Path | None = typer.Option(
        None,
        help="Optional override directory containing anchor essays",
    ),
) -> None:
    """One-time helper to register ENG5 anchors with the CJ service."""

    if not cj_service_url:
        typer.echo("CJ service URL is required for anchor registration", err=True)
        raise typer.Exit(code=1)

    repo_root = repo_root_from_package()
    paths = RunnerPaths.from_repo_root(repo_root)

    if anchor_dir:
        anchor_snapshot = snapshot_directory(anchor_dir, ("*.docx", "*.txt"))
        anchors = anchor_snapshot.files
    else:
        anchors = collect_inventory(paths).anchor_docs.files

    if not anchors:
        typer.echo("No anchor essays found for registration", err=True)
        raise typer.Exit(code=1)

    typer.echo(
        f"Registering {len(anchors)} anchors with assignment {assignment_id}",
        err=True,
    )
    try:
        results = asyncio.run(
            register_anchor_essays(
                anchors=anchors,
                assignment_id=assignment_id,
                cj_service_url=cj_service_url,
            )
        )
    except AnchorRegistrationError as exc:
        typer.echo(f"Anchor registration failed: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Successfully registered {len(results)} anchors via {cj_service_url}")


def validate_llm_overrides(
    provider: str | None,
    model: str | None,
) -> None:
    """Validate LLM overrides against model manifest.

    This function checks that the specified model exists in the manifest
    and logs model metadata for transparency. If validation fails, it
    provides helpful guidance to the user.

    Args:
        provider: Provider name (e.g., "anthropic", "openai")
        model: Model identifier to validate

    Raises:
        typer.BadParameter: If model is not found in manifest

    Note:
        This function validates only when model is specified. If model is None,
        no validation is performed (service will use its default).
    """
    if model is None:
        # No model override specified; service will use default
        typer.echo(
            "ℹ️  No --llm-model specified; LLM Provider Service will use default model",
            err=True,
        )
        return

    # Import manifest modules (lazy import to avoid circular dependencies)
    try:
        from services.llm_provider_service.model_manifest import (
            ProviderName,
            get_model_config,
        )
    except ImportError as e:
        typer.echo(
            f"⚠️  Warning: Cannot import model manifest for validation: {e}",
            err=True,
        )
        typer.echo(
            "   Proceeding without validation; service will validate at runtime.",
            err=True,
        )
        return

    # Determine provider (default to Anthropic if not specified)
    provider_name = provider.upper() if provider else "ANTHROPIC"
    try:
        provider_enum = ProviderName(provider_name.lower())
    except ValueError:
        valid_providers = ", ".join(p.value for p in ProviderName if p != ProviderName.MOCK)
        raise typer.BadParameter(
            (
                f"Invalid provider '{provider_name}'. "
                f"Valid providers: {valid_providers}\n"
                "Run 'pdm run llm-check-models' to see available models."
            )
        )

    # Validate model against manifest
    try:
        config = get_model_config(provider_enum, model)

        # Log successful validation with model metadata
        typer.echo(
            "✅ Model validated against manifest:",
            err=True,
        )
        typer.echo(f"   Provider: {config.provider.value}", err=True)
        typer.echo(f"   Model ID: {config.model_id}", err=True)
        typer.echo(f"   Display Name: {config.display_name}", err=True)
        typer.echo(f"   API Version: {config.api_version}", err=True)
        typer.echo(f"   Release Date: {config.release_date}", err=True)
        typer.echo(f"   Max Tokens: {config.max_tokens}", err=True)

        if config.is_deprecated:
            typer.echo(
                f"⚠️  WARNING: Model '{model}' is deprecated (since {config.deprecation_date})",
                err=True,
            )
            if config.notes:
                typer.echo(f"   Note: {config.notes}", err=True)

    except ValueError as e:
        raise typer.BadParameter(
            f"Model '{model}' not found in manifest for provider '{provider_name}'.\n"
            f"Error: {e}\n\n"
            f"To see available models, run:\n"
            f"  pdm run llm-check-models --provider {provider_name.lower()}\n"
        )
    except KeyError as e:
        raise typer.BadParameter(
            f"Provider '{provider_name}' not found in manifest.\n"
            f"Error: {e}\n\n"
            f"To see available providers, run:\n"
            f"  pdm run llm-check-models\n"
        )


def _build_llm_overrides(
    *,
    provider: str | None,
    model: str | None,
    temperature: float | None,
    max_tokens: int | None,
) -> LLMConfigOverrides | None:
    if not any([provider, model, temperature, max_tokens]):
        return None

    provider_value: LLMProviderType | None = None
    if provider:
        try:
            # Normalize to lowercase to match enum values
            provider_value = LLMProviderType(provider.lower())
        except ValueError as e:
            valid_providers = ", ".join(
                p.value for p in LLMProviderType if p != LLMProviderType.MOCK
            )
            # This should have been caught by validate_llm_overrides(), but raise clear error anyway
            raise typer.BadParameter(
                (
                    f"Invalid provider '{provider}'. "
                    f"Valid providers: {valid_providers}\n"
                    "Run 'pdm run llm-check-models' to see available models."
                )
            ) from e

    return LLMConfigOverrides(
        provider_override=provider_value,
        model_override=model,
        temperature_override=temperature,
        max_tokens_override=max_tokens,
    )


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    mode: RunnerMode = typer.Option(RunnerMode.PLAN, case_sensitive=False),
    assignment_id: uuid.UUID = typer.Option(
        ...,
        help="Assignment ID (REQUIRED). Must exist in CJ service assessment_instructions table. "
        "Create via: POST /admin/v1/assessment-instructions",
    ),
    course_id: uuid.UUID = typer.Option(
        ...,
        help="Course ID (REQUIRED). Used for metadata and scope context.",
    ),
    grade_scale: str = typer.Option(
        "eng5_np_legacy_9_step",
        help="Grade scale key registered in the CJ service",
    ),
    batch_id: str = typer.Option(
        "eng5-np-local-batch",
        help="Logical batch identifier propagated to CJ",
    ),
    user_id: str = typer.Option(
        "eng5_np_research_runner",
        help="User ID to include in CJ request",
    ),
    org_id: str | None = typer.Option(
        None,
        help="Optional organization identifier",
    ),
    course_code: CourseCode = typer.Option(  # type: ignore[arg-type]
        CourseCode.ENG5,
        case_sensitive=False,
        help="Course code for CJ request",
    ),
    language: Language = typer.Option(  # type: ignore[arg-type]
        Language.ENGLISH,
        case_sensitive=False,
        help="Essay language (defaults to ENG5 English)",
    ),
    no_kafka: bool = typer.Option(
        False,
        help="Skip Kafka submission even in execute mode",
    ),
    output_dir: Path | None = typer.Option(
        None,
        help="Optional override for artefact output directory",
    ),
    kafka_bootstrap: str = typer.Option(
        os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        help="Kafka bootstrap servers (host:port, comma separated)",
    ),
    kafka_client_id: str = typer.Option(
        "eng5-np-runner",
        help="Kafka client_id to use when publishing",
    ),
    cj_service_url: str | None = typer.Option(
        os.getenv("CJ_SERVICE_URL"),
        help="CJ Assessment Service base URL for anchor registration",
    ),
    content_service_url: str = typer.Option(
        os.getenv("CONTENT_SERVICE_URL", "http://localhost:8001/v1/content"),
        help="Content Service upload endpoint",
    ),
    llm_provider: str | None = typer.Option(
        None,
        help="Override LLM provider (e.g., openai, anthropic)",
    ),
    llm_model: str | None = typer.Option(
        None,
        help="Override LLM model identifier",
    ),
    llm_temperature: float | None = typer.Option(
        None,
        min=0.0,
        max=2.0,
        help="Override temperature (0.0-2.0)",
    ),
    llm_max_tokens: int | None = typer.Option(
        None,
        min=1,
        help="Override max completion tokens",
    ),
    max_comparisons: int | None = typer.Option(
        None,
        min=1,
        help="Limit total comparisons (for testing/cost control)",
    ),
    await_completion: bool = typer.Option(
        False,
        help="Wait for CJ completion event before exiting",
    ),
    completion_timeout: float = typer.Option(
        1800.0,
        help="Timeout (seconds) when waiting for completion events",
    ),
    verbose: bool = typer.Option(
        False,
        help="Enable debug-level logging for troubleshooting",
    ),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    repo_root = repo_root_from_package()
    paths = RunnerPaths.from_repo_root(repo_root)

    configure_cli_logging(verbose=verbose)

    # Validate LLM model override against manifest before proceeding
    validate_llm_overrides(provider=llm_provider, model=llm_model)

    settings = RunnerSettings(
        assignment_id=assignment_id,
        course_id=course_id,
        grade_scale=grade_scale,
        mode=mode,
        use_kafka=not no_kafka,
        output_dir=output_dir or paths.artefact_output_dir,
        runner_version=__version__,
        git_sha=gather_git_sha(repo_root),
        batch_id=batch_id,
        user_id=user_id,
        org_id=org_id,
        course_code=course_code,
        language=language,
        correlation_id=uuid.uuid4(),
        kafka_bootstrap=kafka_bootstrap,
        kafka_client_id=kafka_client_id,
        cj_service_url=cj_service_url,
        content_service_url=content_service_url,
        llm_overrides=_build_llm_overrides(
            provider=llm_provider,
            model=llm_model,
            temperature=llm_temperature,
            max_tokens=llm_max_tokens,
        ),
        max_comparisons=max_comparisons,
        await_completion=await_completion,
        completion_timeout=completion_timeout,
    )

    logger = setup_cli_logger(settings=settings)

    logger.info(
        "runner_invocation",
        assignment_id=str(settings.assignment_id),
        course_id=str(settings.course_id),
        use_kafka=settings.use_kafka,
        await_completion=settings.await_completion,
        output_dir=str(settings.output_dir),
        kafka_bootstrap=settings.kafka_bootstrap,
        verbose=verbose,
    )

    inventory = collect_inventory(paths)

    if mode is RunnerMode.PLAN:
        logger.info(
            "runner_plan_inventory",
            anchor_count=inventory.anchor_docs.count,
            student_count=inventory.student_docs.count,
            prompt_path=str(inventory.prompt.path),
        )
        print_inventory(inventory)
        plan_snapshot = {
            "validation": {
                "manifest": [],
                "artefact_checksum": None,
                "runner_status": {
                    "mode": RunnerMode.PLAN.value,
                    "partial_data": False,
                    "timeout_seconds": 0.0,
                    "observed_events": {
                        "llm_comparisons": 0,
                        "assessment_results": 0,
                        "completions": 0,
                    },
                    "inventory": {
                        "anchors": inventory.anchor_docs.count,
                        "students": inventory.student_docs.count,
                        "prompt_path": str(inventory.prompt.path),
                    },
                },
            }
        }
        log_validation_state(
            logger=logger,
            artefact_path=settings.output_dir / f"assessment_run.{RunnerMode.PLAN.value}.json",
            artefact_data=plan_snapshot,
        )
        return

    schema = ensure_schema_available(paths.schema_path)

    artefact_path = write_stub_artefact(settings=settings, inventory=inventory, schema=schema)
    hydrator: AssessmentRunHydrator | None = None
    if settings.await_completion and settings.use_kafka:
        hydrator = AssessmentRunHydrator(
            artefact_path=artefact_path,
            output_dir=settings.output_dir,
            grade_scale=settings.grade_scale,
            batch_id=settings.batch_id,
        )

    if mode is RunnerMode.DRY_RUN:
        logger.info(
            "runner_dry_run_stub_created",
            artefact_path=str(artefact_path),
        )
        log_validation_state(
            logger=logger,
            artefact_path=artefact_path,
            artefact_data=load_artefact_data(artefact_path),
        )
        return

    if mode is RunnerMode.EXECUTE:
        ensure_execute_requirements(inventory)
        limited_anchors, limited_students, _ = apply_comparison_limit(
            anchors=inventory.anchor_docs.files,
            students=inventory.student_docs.files,
            max_comparisons=settings.max_comparisons,
            emit_notice=False,
        )
        anchors_for_registration = inventory.anchor_docs.files
        anchor_registration_used = False
        if settings.cj_service_url and anchors_for_registration:
            try:
                registration_results = asyncio.run(
                    register_anchor_essays(
                        anchors=anchors_for_registration,
                        assignment_id=settings.assignment_id,
                        cj_service_url=settings.cj_service_url,
                    )
                )
                if registration_results:
                    anchor_registration_used = True
                    typer.echo(
                        f"Registered {len(registration_results)} anchors via CJ service",
                        err=True,
                    )
                    logger.info(
                        "anchor_registration_succeeded",
                        registered=len(registration_results),
                    )
            except AnchorRegistrationError as exc:
                typer.echo(
                    f"⚠ Anchor registration failed: {exc}. Falling back to ephemeral anchors.",
                    err=True,
                )
                logger.warning(
                    "anchor_registration_failed",
                    error=str(exc),
                )

        if anchor_registration_used:
            upload_targets = limited_students
        else:
            upload_targets = [*limited_anchors, *limited_students]
        if not upload_targets:
            raise RuntimeError("No essays available for upload; ensure dataset is populated")
        typer.echo(
            f"Uploading {len(upload_targets)} essays to Content Service at {settings.content_service_url}",
            err=True,
        )
        storage_id_map = asyncio.run(
            upload_essays_parallel(
                records=upload_targets,
                content_service_url=settings.content_service_url,
            )
        )
        if anchor_registration_used:
            essay_ref_anchors: list[FileRecord] = []
            essay_ref_students = limited_students
        else:
            essay_ref_anchors = limited_anchors
            essay_ref_students = limited_students

        essay_refs = build_essay_refs(
            anchors=essay_ref_anchors,
            students=essay_ref_students,
            max_comparisons=None,
            storage_id_map=storage_id_map,
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
            except Exception as exc:  # pragma: no cover - side effect only
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

    log_validation_state(
        logger=logger,
        artefact_path=artefact_path,
        artefact_data=load_artefact_data(artefact_path),
    )


if __name__ == "__main__":
    app()
