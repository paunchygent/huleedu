"""Typer CLI entrypoint for the ENG5 NP batch runner.

Implements a handler-based architecture where each runner mode (PLAN, DRY_RUN,
ANCHOR_ALIGN_TEST, EXECUTE) has a dedicated handler class. This keeps the CLI
thin (~350 lines) while mode-specific logic lives in handlers/ (~100-350 lines each).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import typer
from common_core import LLMProviderType
from common_core.domain_enums import CourseCode, Language
from common_core.events.cj_assessment_events import LLMConfigOverrides

from scripts.cj_experiments_runners.eng5_np import __version__
from scripts.cj_experiments_runners.eng5_np.anchors_preflight import (
    AnchorPreflightAuthError,
    AnchorPreflightConfigError,
    AnchorPreflightMissingAnchorsError,
    AnchorPreflightNotFoundError,
    resolve_anchor_preflight,
)
from scripts.cj_experiments_runners.eng5_np.assignment_preflight import (
    AssignmentPreflightAuthError,
    AssignmentPreflightConfigError,
    AssignmentPreflightNotFoundError,
    resolve_assignment_preflight,
)
from scripts.cj_experiments_runners.eng5_np.cj_client import (
    AnchorRegistrationError,
    register_anchor_essays,
)
from scripts.cj_experiments_runners.eng5_np.environment import (
    gather_git_sha,
    repo_root_from_package,
)
from scripts.cj_experiments_runners.eng5_np.handlers import (
    AnchorAlignHandler,
    DryRunHandler,
    ExecuteHandler,
    PlanHandler,
)
from scripts.cj_experiments_runners.eng5_np.inventory import (
    ComparisonValidationError,
    collect_inventory,
    ensure_comparison_capacity,
    ensure_comparison_capacity_counts,
    snapshot_directory,
)
from scripts.cj_experiments_runners.eng5_np.logging_support import (
    configure_cli_logging,
    configure_execute_logging,
    setup_cli_logger,
)
from scripts.cj_experiments_runners.eng5_np.paths import RunnerPaths
from scripts.cj_experiments_runners.eng5_np.settings import RunnerMode, RunnerSettings
from scripts.cj_experiments_runners.eng5_np.system_prompt import build_cj_system_prompt

# Handler dispatch map - each mode has a dedicated handler class
HANDLER_MAP: dict[RunnerMode, type] = {
    RunnerMode.PLAN: PlanHandler,
    RunnerMode.DRY_RUN: DryRunHandler,
    RunnerMode.ANCHOR_ALIGN_TEST: AnchorAlignHandler,
    RunnerMode.EXECUTE: ExecuteHandler,
}

_DEFAULT_GRADE_SCALE = "eng5_np_legacy_9_step"

app = typer.Typer(
    help="ENG5 NP batch runner tooling (plan, dry-run, execute)\n\n"
    "AUTH: Development auto-generates admin tokens. "
    "Production requires HULEEDU_SERVICE_ACCOUNT_TOKEN env var."
)


@app.command("register-anchors")
def register_anchors_command(
    assignment_id: uuid.UUID = typer.Argument(..., help="Assignment ID to bind anchors to"),
    cj_service_url: str = typer.Option(
        os.getenv("CJ_SERVICE_URL", "http://localhost:9095"),
        help="CJ Assessment Service base URL",
    ),
    expected_grade_scale: str | None = typer.Option(
        None,
        "--expected-grade-scale",
        help=(
            "Optional assertion for CJ-owned grade scale. When provided, the runner "
            "will resolve grade_scale from CJ assessment_instructions and fail fast "
            "if it does not match."
        ),
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

    try:
        preflight = resolve_assignment_preflight(
            assignment_id=assignment_id,
            cj_service_url=cj_service_url,
        )
    except (
        AssignmentPreflightAuthError,
        AssignmentPreflightConfigError,
        AssignmentPreflightNotFoundError,
    ) as exc:
        typer.echo(f"Assignment preflight failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        "Resolved assignment context from CJ: "
        f"assignment_id={preflight.assignment_id} grade_scale={preflight.grade_scale}",
        err=True,
    )
    if expected_grade_scale is not None and expected_grade_scale != preflight.grade_scale:
        typer.echo(
            "Expected grade_scale mismatch. "
            f"Expected '{expected_grade_scale}', but CJ has '{preflight.grade_scale}' "
            f"for assignment_id={preflight.assignment_id}.",
            err=True,
        )
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


@app.command("verify-auth")
def verify_auth_command() -> None:
    """Verify JWT authentication configuration and production safety."""
    try:
        import jwt

        from scripts.cj_experiments_runners.eng5_np.cj_client import build_admin_headers

        headers = build_admin_headers()
        token = headers["Authorization"].replace("Bearer ", "")

        # Decode without verification (just inspect claims)
        claims = jwt.decode(token, options={"verify_signature": False})

        typer.echo("✅ Authentication working:")
        typer.echo(f"   Subject: {claims.get('sub')}")
        typer.echo(f"   Roles: {claims.get('roles')}")
        typer.echo(f"   Issuer: {claims.get('iss')}")
        typer.echo(f"   Audience: {claims.get('aud')}")

        from datetime import datetime

        exp_dt = datetime.fromtimestamp(claims["exp"])
        typer.echo(f"   Expires: {exp_dt}")

    except RuntimeError as e:
        if "production" in str(e).lower():
            typer.echo(
                "✅ Production safety ACTIVE - dev auth blocked",
                err=True,
            )
            typer.echo(
                "   Set HULEEDU_SERVICE_ACCOUNT_TOKEN to authenticate",
                err=True,
            )
        else:
            typer.echo(f"❌ Error: {e}", err=True)
            raise typer.Exit(1)


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
    system_prompt: str | None,
    judge_rubric_override: str | None = None,
    reasoning_effort: str | None = None,
    output_verbosity: str | None = None,
) -> LLMConfigOverrides | None:
    if not any(
        [
            provider,
            model,
            temperature,
            max_tokens,
            system_prompt,
            judge_rubric_override,
            reasoning_effort,
            output_verbosity,
        ]
    ):
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
        system_prompt_override=system_prompt,
        judge_rubric_override=judge_rubric_override,
        reasoning_effort=reasoning_effort,
        output_verbosity=output_verbosity,
    )


def _load_prompt_file(path: Path | None, label: str) -> str | None:
    if path is None:
        return None
    if not path.exists():
        raise typer.BadParameter(f"{label} file not found: {path}")
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise typer.BadParameter(f"{label} file is empty: {path}")
    typer.echo(f"Loaded {label}: {path} ({len(content)} chars)", err=True)
    return content


def _parse_course_code(raw: str) -> CourseCode:
    normalized = raw.strip().upper()
    try:
        return CourseCode(normalized)
    except ValueError as exc:
        valid = ", ".join(sorted(code.value for code in CourseCode))
        raise typer.BadParameter(
            f"Invalid --course-code value: {raw!r}. Valid values are: {valid}.",
            param_hint="'--course-code'",
        ) from exc


def _parse_language(raw: str) -> Language:
    normalized = raw.strip().lower()
    for lang in Language:
        if normalized == lang.value.lower():
            return lang

    valid = ", ".join(sorted(lang.value for lang in Language))
    raise typer.BadParameter(
        f"Invalid --language value: {raw!r}. Valid values are: {valid}.",
        param_hint="'--language'",
    )


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    mode: RunnerMode = typer.Option(
        RunnerMode.PLAN,
        case_sensitive=False,
        help="Runner mode: plan (preview only), dry_run (stub creation), execute (full run with "
        "persistent file logging enabled at .claude/research/data/eng5_np_2016/logs/)",
    ),
    assignment_id: uuid.UUID | None = typer.Option(
        None,
        help="Assignment ID. Required for execute mode. "
        "Create via: POST /admin/v1/assessment-instructions",
    ),
    course_id: uuid.UUID | None = typer.Option(
        None,
        help="Course ID. Required for execute mode. Used for metadata and scope context.",
    ),
    expected_grade_scale: str | None = typer.Option(
        None,
        "--expected-grade-scale",
        help=(
            "Optional assertion for CJ-owned grade scale. When provided (and when "
            "--assignment-id is provided), the runner resolves grade_scale from CJ "
            "assessment_instructions and fails fast if it does not match."
        ),
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
    course_code: str = typer.Option(
        CourseCode.ENG5.value,
        case_sensitive=False,
        help="Course code for CJ request (e.g., ENG5, ENG6, SV1)",
    ),
    language: str = typer.Option(
        Language.ENGLISH.value,
        case_sensitive=False,
        help="Essay language (e.g., en, sv)",
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
        os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9093"),
        help="Kafka bootstrap servers (host:port, comma separated)",
    ),
    kafka_client_id: str = typer.Option(
        "eng5-np-runner",
        help="Kafka client_id to use when publishing",
    ),
    cj_service_url: str | None = typer.Option(
        os.getenv("CJ_SERVICE_URL"),
        help="CJ Assessment Service base URL (required for execute preflight and register-anchors)",
    ),
    content_service_url: str = typer.Option(
        os.getenv("CONTENT_SERVICE_URL", "http://localhost:8001/v1/content"),
        help="Content Service upload endpoint",
    ),
    force_reupload: bool = typer.Option(
        False,
        "--force-reupload",
        help=(
            "Re-upload all essays even if a cached storage_id exists. This refreshes the "
            "disk-backed upload cache stored under the runner output directory."
        ),
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
    cj_system_prompt: bool = typer.Option(
        True,
        "--cj-system-prompt/--no-cj-system-prompt",
        help="Embed the ENG5 Comparative Judgement system prompt override in each LLM request.",
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
    auto_extract_eng5_db: bool = typer.Option(
        False,
        "--auto-extract-eng5-db",
        help=(
            "After a successful completion event (requires --await-completion), "
            "run the CJ DB extraction helper and capture output under the run artefacts."
        ),
    ),
    completion_timeout: float = typer.Option(
        1800.0,
        help="Timeout (seconds) when waiting for completion events",
    ),
    verbose: bool = typer.Option(
        False,
        help="Enable debug-level logging for troubleshooting",
    ),
    llm_batching_mode: str | None = typer.Option(
        None,
        help=(
            "Hint for CJ/LPS LLM batching mode: per_request, serial_bundle, "
            "provider_batch_api. This does not directly change service "
            "configuration; services remain authoritative via their own env "
            "vars. If you are using this runner via an AI assistant or "
            "automation, you must consult a human operator before deciding "
            "or changing this mode."
        ),
    ),
    anchor_align_provider: str | None = typer.Option(
        None,
        "--anchor-align-provider",
        help="Override LLM provider for anchor-align-test (e.g., anthropic, openai).",
    ),
    anchor_align_model: str | None = typer.Option(
        None,
        "--anchor-align-model",
        help="Override LLM model identifier for anchor-align-test.",
    ),
    anchor_align_reasoning_effort: str | None = typer.Option(
        None,
        "--anchor-align-reasoning-effort",
        help="Reasoning effort for GPT-5.1 anchor-align runs: none, low, medium, high.",
    ),
    anchor_align_output_verbosity: str | None = typer.Option(
        None,
        "--anchor-align-output-verbosity",
        help="Output verbosity for GPT-5.1 anchor-align runs: low, medium, high.",
    ),
    # Anchor alignment test mode options
    system_prompt_file: Path | None = typer.Option(
        None,
        "--system-prompt",
        help="Path to custom system prompt file (execute or anchor-align-test mode)",
    ),
    rubric_file: Path | None = typer.Option(
        None,
        "--rubric",
        help="Path to custom judge rubric file (execute or anchor-align-test mode)",
    ),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    # Validate required options based on mode
    if mode is RunnerMode.EXECUTE:
        if assignment_id is None:
            raise typer.BadParameter(
                "--assignment-id is required for execute mode",
                param_hint="'--assignment-id'",
            )
        if course_id is None:
            raise typer.BadParameter(
                "--course-id is required for execute mode",
                param_hint="'--course-id'",
            )

    if mode is not RunnerMode.ANCHOR_ALIGN_TEST and any(
        [
            anchor_align_provider,
            anchor_align_model,
            anchor_align_reasoning_effort,
            anchor_align_output_verbosity,
        ]
    ):
        raise typer.BadParameter(
            "Anchor-align specific flags can only be used with --mode anchor-align-test"
        )

    if mode not in {RunnerMode.ANCHOR_ALIGN_TEST, RunnerMode.EXECUTE} and any(
        [system_prompt_file, rubric_file]
    ):
        raise typer.BadParameter(
            "--system-prompt/--rubric can only be used with execute or anchor-align-test"
        )

    repo_root = repo_root_from_package()
    paths = RunnerPaths.from_repo_root(repo_root)

    configure_cli_logging(verbose=verbose)

    if expected_grade_scale is not None and assignment_id is None:
        raise typer.BadParameter(
            "--expected-grade-scale requires --assignment-id so the runner can "
            "validate against CJ assessment_instructions.",
            param_hint="'--expected-grade-scale'",
        )

    if auto_extract_eng5_db and not await_completion:
        raise typer.BadParameter(
            "--auto-extract-eng5-db requires --await-completion.",
            param_hint="'--auto-extract-eng5-db'",
        )
    if auto_extract_eng5_db and no_kafka:
        raise typer.BadParameter(
            "--auto-extract-eng5-db requires Kafka publishing (omit --no-kafka).",
            param_hint="'--auto-extract-eng5-db'",
        )

    resolved_grade_scale = _DEFAULT_GRADE_SCALE
    cj_anchor_count: int | None = None
    assignment_context_origin: str | None = None
    if assignment_id is not None:
        try:
            preflight = resolve_assignment_preflight(
                assignment_id=assignment_id,
                cj_service_url=cj_service_url,
            )
        except AssignmentPreflightConfigError as exc:
            raise typer.BadParameter(str(exc), param_hint="'--cj-service-url'") from exc
        except AssignmentPreflightNotFoundError as exc:
            raise typer.BadParameter(str(exc), param_hint="'--assignment-id'") from exc
        except AssignmentPreflightAuthError as exc:
            raise typer.BadParameter(str(exc)) from exc

        resolved_grade_scale = preflight.grade_scale
        assignment_context_origin = preflight.context_origin
        typer.echo(
            "Resolved assignment context from CJ: "
            f"assignment_id={preflight.assignment_id} "
            f"grade_scale={preflight.grade_scale} "
            f"context_origin={preflight.context_origin} "
            f"student_prompt={'present' if preflight.student_prompt_storage_id else 'missing'}",
            err=True,
        )

        if mode is RunnerMode.EXECUTE and preflight.student_prompt_storage_id is None:
            raise typer.BadParameter(
                "CJ assessment_instructions is missing a student prompt for this assignment. "
                "Upload one via the CJ admin API/CLI before running execute, e.g. "
                "`pdm run cj-admin prompts upload --assignment-id ... --prompt-file ...`.",
                param_hint="'--assignment-id'",
            )

        if (
            expected_grade_scale is not None
            and expected_grade_scale.strip() != ""
            and expected_grade_scale != preflight.grade_scale
        ):
            raise typer.BadParameter(
                "Expected grade_scale mismatch. "
                f"Expected '{expected_grade_scale}', but CJ has '{preflight.grade_scale}' "
                f"for assignment_id={preflight.assignment_id}.",
                param_hint="'--expected-grade-scale'",
            )

        if mode is RunnerMode.EXECUTE:
            if assignment_context_origin == "canonical_national" and rubric_file is not None:
                raise typer.BadParameter(
                    "Rubric override is not allowed for canonical assignments. "
                    "Update CJ assessment_instructions.context_origin to a non-canonical value "
                    "(e.g. 'research_experiment') before running rubric A/B tests.",
                    param_hint="'--rubric'",
                )

            try:
                anchor_preflight = resolve_anchor_preflight(
                    assignment_id=assignment_id,
                    cj_service_url=cj_service_url,
                )
            except AnchorPreflightConfigError as exc:
                raise typer.BadParameter(str(exc), param_hint="'--cj-service-url'") from exc
            except AnchorPreflightNotFoundError as exc:
                raise typer.BadParameter(str(exc), param_hint="'--assignment-id'") from exc
            except AnchorPreflightAuthError as exc:
                raise typer.BadParameter(str(exc)) from exc
            except AnchorPreflightMissingAnchorsError as exc:
                raise typer.BadParameter(str(exc), param_hint="'--assignment-id'") from exc

            cj_anchor_count = anchor_preflight.anchor_count
            typer.echo(
                "Resolved CJ anchor precondition: "
                f"assignment_id={anchor_preflight.assignment_id} "
                f"grade_scale={anchor_preflight.grade_scale} "
                f"anchors={anchor_preflight.anchor_count} "
                f"(total={anchor_preflight.anchor_count_total})",
                err=True,
            )

    if llm_batching_mode is not None:
        typer.echo(
            "⚠️  LLM batching mode hint set to "
            f"'{llm_batching_mode}'. This is an advanced rollout control.\n"
            "   Services remain authoritative via their own env vars "
            "(CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE, "
            "LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE).\n"
            "   If you are using this runner via an AI assistant or "
            "automation, you must consult a human operator before "
            "changing batching modes.",
            err=True,
        )

    effective_llm_provider = llm_provider
    effective_llm_model = llm_model

    anchor_align_llm_provider_value: str | None = None
    anchor_align_llm_model_value: str | None = None
    anchor_align_reasoning_effort_value: str | None = None
    anchor_align_output_verbosity_value: str | None = None

    if mode is RunnerMode.ANCHOR_ALIGN_TEST:
        if anchor_align_provider is not None:
            effective_llm_provider = anchor_align_provider
        if anchor_align_model is not None:
            effective_llm_model = anchor_align_model

        if anchor_align_reasoning_effort is not None:
            normalized_effort = anchor_align_reasoning_effort.lower()
            valid_efforts = {"none", "low", "medium", "high"}
            if normalized_effort not in valid_efforts:
                raise typer.BadParameter(
                    "Invalid --anchor-align-reasoning-effort; valid values are: none, low, medium, high.",  # noqa: E501
                    param_hint="'--anchor-align-reasoning-effort'",
                )
            anchor_align_reasoning_effort_value = normalized_effort

        if anchor_align_output_verbosity is not None:
            normalized_verbosity = anchor_align_output_verbosity.lower()
            valid_verbosity = {"low", "medium", "high"}
            if normalized_verbosity not in valid_verbosity:
                raise typer.BadParameter(
                    "Invalid --anchor-align-output-verbosity; valid values are: low, medium, high.",  # noqa: E501
                    param_hint="'--anchor-align-output-verbosity'",
                )
            anchor_align_output_verbosity_value = normalized_verbosity

        anchor_align_llm_provider_value = effective_llm_provider
        anchor_align_llm_model_value = effective_llm_model

    # Validate LLM model override against manifest before proceeding
    validate_llm_overrides(provider=effective_llm_provider, model=effective_llm_model)

    rubric_text_override = (
        _load_prompt_file(rubric_file, "judge rubric") if mode is RunnerMode.EXECUTE else None
    )

    system_prompt_override = None
    if mode is RunnerMode.EXECUTE:
        system_prompt_override = _load_prompt_file(system_prompt_file, "system prompt")
        if system_prompt_override is None and cj_system_prompt:
            system_prompt_override = build_cj_system_prompt()
    else:
        system_prompt_override = build_cj_system_prompt() if cj_system_prompt else None

    course_code_value = _parse_course_code(course_code)
    language_value = _parse_language(language)

    settings = RunnerSettings(
        assignment_id=assignment_id,
        cj_assignment_id=None if mode is RunnerMode.ANCHOR_ALIGN_TEST else assignment_id,
        course_id=course_id,
        grade_scale=resolved_grade_scale,
        cj_anchor_count=cj_anchor_count,
        mode=mode,
        use_kafka=not no_kafka,
        output_dir=output_dir or paths.artefact_output_dir,
        runner_version=__version__,
        git_sha=gather_git_sha(repo_root),
        batch_uuid=uuid.uuid4(),
        batch_id=batch_id,
        user_id=user_id,
        org_id=org_id,
        course_code=course_code_value,
        language=language_value,
        correlation_id=uuid.uuid4(),
        kafka_bootstrap=kafka_bootstrap,
        kafka_client_id=kafka_client_id,
        cj_service_url=cj_service_url,
        content_service_url=content_service_url,
        force_reupload=force_reupload,
        llm_overrides=_build_llm_overrides(
            provider=effective_llm_provider,
            model=effective_llm_model,
            temperature=llm_temperature,
            max_tokens=llm_max_tokens,
            system_prompt=system_prompt_override,
            judge_rubric_override=rubric_text_override,
            reasoning_effort=anchor_align_reasoning_effort_value,
            output_verbosity=anchor_align_output_verbosity_value,
        ),
        max_comparisons=max_comparisons,
        await_completion=await_completion,
        auto_extract_eng5_db=auto_extract_eng5_db,
        completion_timeout=completion_timeout,
        llm_batching_mode_hint=llm_batching_mode,
        system_prompt_file=system_prompt_file,
        rubric_file=rubric_file,
        anchor_align_llm_provider=anchor_align_llm_provider_value,
        anchor_align_llm_model=anchor_align_llm_model_value,
        anchor_align_reasoning_effort=anchor_align_reasoning_effort_value,
        anchor_align_output_verbosity=anchor_align_output_verbosity_value,
    )

    # Reconfigure logging for execute mode to enable file persistence
    if mode is RunnerMode.EXECUTE:
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = (
            f".claude/research/data/eng5_np_2016/logs/eng5-{settings.batch_id}-{timestamp}.log"
        )
        configure_execute_logging(settings=settings, verbose=verbose)
        typer.echo(
            f"📝 Execute mode: Persistent logging enabled → {log_file}",
            err=True,
        )

    logger = setup_cli_logger(settings=settings)

    typer.echo(
        f"Canonical batch UUID: {settings.batch_uuid} (label: {settings.batch_id})",
        err=True,
    )

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

    try:
        if mode is RunnerMode.EXECUTE:
            ensure_comparison_capacity_counts(
                anchor_count=settings.cj_anchor_count or 0,
                student_count=inventory.student_docs.count,
                max_comparisons=settings.max_comparisons,
                anchors_hint="CJ anchors (admin preflight)",
                students_hint=str(inventory.student_docs.root),
            )
        else:
            ensure_comparison_capacity(
                anchors=inventory.anchor_docs,
                students=inventory.student_docs,
                max_comparisons=settings.max_comparisons,
            )
    except ComparisonValidationError as exc:
        typer.echo("❌ Comparison validation failed:", err=True)
        typer.echo(f"   {exc}", err=True)
        if mode is RunnerMode.EXECUTE:
            typer.echo(f"   CJ anchors found: {settings.cj_anchor_count or 0}", err=True)
        else:
            typer.echo(
                f"   Anchors found: {inventory.anchor_docs.count} in {inventory.anchor_docs.root}",
                err=True,
            )
        typer.echo(
            f"   Students found: {inventory.student_docs.count} in {inventory.student_docs.root}",
            err=True,
        )
        raise typer.Exit(code=1)

    if settings.max_comparisons is not None:
        logger.info(
            "runner_max_comparisons_requested",
            max_comparisons=settings.max_comparisons,
        )

    # Dispatch to mode-specific handler
    handler_class = HANDLER_MAP.get(mode)
    if handler_class is None:
        raise typer.BadParameter(f"Unknown mode: {mode}")

    handler = handler_class()
    exit_code = handler.execute(settings=settings, inventory=inventory, paths=paths)
    raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()
