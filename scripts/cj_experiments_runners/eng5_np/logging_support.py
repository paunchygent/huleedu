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


def configure_execute_logging(*, settings: RunnerSettings, verbose: bool) -> None:
    """Configure file + stdout logging for execute mode runs.

    Creates persistent log files in .claude/research/data/eng5_np_2016/logs/
    with the pattern: eng5-{batch_id}-{timestamp}.log

    Uses service-standard rotation: 100MB per file, 10 backups (1GB total).
    """
    from datetime import datetime

    log_dir = Path(".claude/research/data/eng5_np_2016/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"eng5-{settings.batch_id}-{timestamp}.log"

    configure_service_logging(
        service_name="eng5-np-runner",
        environment="production",
        log_level="DEBUG" if verbose else "INFO",
        log_to_file=True,
        log_file_path=str(log_file),
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


def print_batching_metrics_hints(*, llm_batching_mode_hint: str | None) -> None:
    """Print Prometheus query hints for LLM batching and serial-bundle metrics.

    These hints are intended for execute-mode runs once CJ and LLM Provider are
    talking to real providers rather than mocks. They do *not* query Prometheus
    directly, only print example queries operators can paste into Grafana.
    """

    mode_label = llm_batching_mode_hint or "(none – services use their own defaults)"

    print("", flush=True)
    print("LLM batching diagnostics (Prometheus query hints)")
    print(f"  Requested CJ LLM batching mode hint: {mode_label}")
    print("  NOTE: Use these in environments where LLM Provider calls real APIs, not mocks.")

    print("\n  # CJ batching usage by mode (5m rate)")
    print("  sum by (batching_mode)(rate(cj_llm_requests_total[5m]))")
    print("  sum by (batching_mode)(rate(cj_llm_batches_started_total[5m]))")

    print("\n  # LLM Provider serial-bundle usage by provider/model (5m rate)")
    print("  sum by (provider, model)(rate(llm_provider_serial_bundle_calls_total[5m]))")
    print("  avg_over_time(llm_provider_serial_bundle_items_per_call[5m])")

    print("\n  # Queue latency and expiry (serial_bundle focus, 5m rate)")
    print(
        "  sum by (queue_processing_mode, result) (rate(llm_provider_queue_wait_time_seconds[5m]))"
    )
    print(
        "  sum by (provider, queue_processing_mode, expiry_reason) "
        "(rate(llm_provider_queue_expiry_total[5m]))"
    )


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
