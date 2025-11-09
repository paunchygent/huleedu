"""Typer CLI entrypoint for the ENG5 NP batch runner."""

from __future__ import annotations

import asyncio
import json
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
from scripts.cj_experiments_runners.eng5_np.environment import (
    gather_git_sha,
    repo_root_from_package,
)
from scripts.cj_experiments_runners.eng5_np.hydrator import AssessmentRunHydrator
from scripts.cj_experiments_runners.eng5_np.inventory import (
    build_essay_refs,
    collect_inventory,
    ensure_execute_requirements,
    print_inventory,
)
from scripts.cj_experiments_runners.eng5_np.kafka_flow import (
    publish_envelope_to_kafka,
    run_publish_and_capture,
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
        raise typer.BadParameter(
            f"Invalid provider '{provider_name}'. "
            f"Valid providers: {', '.join(p.value for p in ProviderName if p != ProviderName.MOCK)}\n"
            f"Run 'pdm run llm-check-models' to see available models."
        )

    # Validate model against manifest
    try:
        config = get_model_config(provider_enum, model)

        # Log successful validation with model metadata
        typer.echo(
            f"✅ Model validated against manifest:",
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
            # This should have been caught by validate_llm_overrides(), but raise clear error anyway
            raise typer.BadParameter(
                f"Invalid provider '{provider}'. "
                f"Valid providers: {', '.join(p.value for p in LLMProviderType if p != LLMProviderType.MOCK)}\n"
                f"Run 'pdm run llm-check-models' to see available models."
            ) from e

    return LLMConfigOverrides(
        provider_override=provider_value,
        model_override=model,
        temperature_override=temperature,
        max_tokens_override=max_tokens,
    )


@app.command()
def main(
    mode: RunnerMode = typer.Option(RunnerMode.PLAN, case_sensitive=False),
    assignment_id: uuid.UUID = typer.Option(
        uuid.UUID("11111111-1111-1111-1111-111111111111"),
        help="Assignment ID for metadata (defaults to ENG5 placeholder)",
    ),
    course_id: uuid.UUID = typer.Option(
        uuid.UUID("22222222-2222-2222-2222-222222222222"),
        help="Course ID for metadata (defaults to ENG5 placeholder)",
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
    await_completion: bool = typer.Option(
        False,
        help="Wait for CJ completion event before exiting",
    ),
    completion_timeout: float = typer.Option(
        1800.0,
        help="Timeout (seconds) when waiting for completion events",
    ),
) -> None:
    repo_root = repo_root_from_package()
    paths = RunnerPaths.from_repo_root(repo_root)
    inventory = collect_inventory(paths)

    if mode is RunnerMode.PLAN:
        print_inventory(inventory)
        return

    schema = ensure_schema_available(paths.schema_path)

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
    hydrator: AssessmentRunHydrator | None = None
    if settings.await_completion and settings.use_kafka:
        hydrator = AssessmentRunHydrator(
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
                    _print_run_summary(artefact_path)
                else:
                    asyncio.run(publish_envelope_to_kafka(envelope=envelope, settings=settings))
                    typer.echo(
                        "Kafka publish succeeded -> topic "
                        f"{topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED)}"
                    )
            except Exception as exc:  # pragma: no cover - side effect only
                typer.echo(
                    f"Kafka publish failed ({exc.__class__.__name__}: {exc}). "
                    "Use --no-kafka to skip publishing.",
                    err=True,
                )
                raise
        else:
            typer.echo("Kafka disabled; request not published.")


def _print_run_summary(artefact_path: Path) -> None:
    """Emit a concise summary of the hydrated artefact for operator awareness."""

    try:
        data = json.loads(artefact_path.read_text(encoding="utf-8"))
    except FileNotFoundError:  # pragma: no cover - defensive
        typer.echo(f"⚠️  Artefact {artefact_path} missing; skipping summary", err=True)
        return

    comparisons = len(data.get("llm_comparisons", []))
    total_cost = data.get("costs", {}).get("total_usd", 0.0)
    typer.echo(
        f"ENG5 NP run captured {comparisons} comparisons; total LLM cost ${total_cost:.4f}"
    )

    for entry in data.get("costs", {}).get("token_counts", []):
        provider = entry.get("provider")
        model = entry.get("model")
        typer.echo(
            "  · "
            f"{provider}::{model}: {entry.get('prompt_tokens', 0)} prompt / "
            f"{entry.get('completion_tokens', 0)} completion tokens, ${entry.get('usd', 0.0):.4f}"
        )

    runner_status = data.get("validation", {}).get("runner_status")
    if runner_status:
        if runner_status.get("partial_data"):
            typer.echo(
                "⚠️  Runner exited with partial data; timeout "
                f"{runner_status.get('timeout_seconds', 0.0)}s",
                err=True,
            )
        observed = runner_status.get("observed_events", {})
        typer.echo(
            "Observed events -> "
            f"comparisons: {observed.get('llm_comparisons', 0)}, "
            f"assessment_results: {observed.get('assessment_results', 0)}, "
            f"completions: {observed.get('completions', 0)}"
        )


if __name__ == "__main__":
    app()
