"""Structured logging helpers for the ENG5 NP runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from huleedu_service_libs.logging_utils import (
    configure_service_logging,
    create_service_logger,
)
from structlog.contextvars import bind_contextvars, clear_contextvars
from structlog.stdlib import BoundLogger

from scripts.cj_experiments_runners.eng5_np.settings import RunnerSettings


def configure_cli_logging(*, verbose: bool) -> None:
    """Configure structlog for the ENG5 NP runner CLI."""

    configure_service_logging(
        service_name="eng5-np-runner",
        environment="production",
        log_level="DEBUG" if verbose else "INFO",
    )


def setup_cli_logger(*, settings: RunnerSettings) -> BoundLogger:
    """Bind correlation context and return a structlog logger for the CLI."""

    clear_contextvars()
    bind_contextvars(
        correlation_id=str(settings.correlation_id),
        batch_id=settings.batch_id,
        batch_uuid=str(settings.batch_uuid),
        runner_mode=settings.mode.value,
    )

    return create_service_logger("eng5_np_cli").bind(
        batch_id=settings.batch_id,
        batch_uuid=str(settings.batch_uuid),
        runner_mode=settings.mode.value,
    )


def load_artefact_data(artefact_path: Path) -> dict[str, Any] | None:
    """Load the assessment artefact from disk if it exists."""

    try:
        return json.loads(artefact_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def print_run_summary(artefact_path: Path) -> dict[str, Any] | None:
    """Emit a concise summary for operators and return the artefact payload."""

    data = load_artefact_data(artefact_path)
    if data is None:
        return None

    comparisons = len(data.get("llm_comparisons", []))
    total_cost = data.get("costs", {}).get("total_usd", 0.0)

    print(f"ENG5 NP run captured {comparisons} comparisons; total LLM cost ${total_cost:.4f}")

    for entry in data.get("costs", {}).get("token_counts", []):
        provider = entry.get("provider")
        model = entry.get("model")
        prompt_tokens = entry.get("prompt_tokens", 0)
        completion_tokens = entry.get("completion_tokens", 0)
        usd = entry.get("usd", 0.0)
        print(
            "  · "
            f"{provider}::{model}: {prompt_tokens} prompt / "
            f"{completion_tokens} completion tokens, ${usd:.4f}"
        )

    runner_status = data.get("validation", {}).get("runner_status")
    if runner_status:
        if runner_status.get("partial_data"):
            timeout = runner_status.get("timeout_seconds", 0.0)
            print(
                f"⚠️  Runner exited with partial data; timeout {timeout}s",
                flush=True,
            )
        observed = runner_status.get("observed_events", {})
        print(
            "Observed events -> "
            f"comparisons: {observed.get('llm_comparisons', 0)}, "
            f"assessment_results: {observed.get('assessment_results', 0)}, "
            f"completions: {observed.get('completions', 0)}"
        )

    return data


def log_validation_state(
    *,
    logger: BoundLogger,
    artefact_path: Path,
    artefact_data: dict[str, Any] | None = None,
) -> None:
    """Log manifest size and runner status for downstream observability."""

    data = artefact_data or load_artefact_data(artefact_path)
    if data is None:
        logger.warning("validation_load_failed", reason="missing_artefact")
        return

    validation = data.get("validation") or {}
    manifest = validation.get("manifest") or []
    logger.info(
        "runner_validation_state",
        manifest_entries=len(manifest),
        artefact_checksum=validation.get("artefact_checksum"),
        runner_status=validation.get("runner_status"),
    )
