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


def _build_llm_overrides(
    *,
    provider: str | None,
    model: str | None,
    temperature: float | None,
    max_tokens: int | None,
) -> LLMConfigOverrides | None:
    if not any([provider, model, temperature, max_tokens]):
        return None

    provider_value: LLMProviderType | str | None = None
    if provider:
        try:
            provider_value = LLMProviderType(provider.upper())
        except Exception:
            provider_value = provider

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

        try:
            if settings.await_completion and settings.use_kafka:
                asyncio.run(
                    run_publish_and_capture(
                        envelope=envelope,
                        settings=settings,
                        hydrator=hydrator,
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
        except Exception as exc:  # pragma: no cover - side effect only
            typer.echo(
                f"Kafka publish failed ({exc.__class__.__name__}: {exc}). "
                "Use --no-kafka to skip publishing.",
                err=True,
            )
            raise


if __name__ == "__main__":
    app()
