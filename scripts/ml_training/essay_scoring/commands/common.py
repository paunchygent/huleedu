"""Shared helpers for essay-scoring CLI commands.

Purpose:
    Centralize configuration loading, override application, and small command
    invariants shared across command modules.

Relationships:
    - Used by command registration modules under
      `scripts.ml_training.essay_scoring.commands`.
    - Depends on `ExperimentConfig` and offload configuration models.
"""

from __future__ import annotations

from pathlib import Path

import typer

from scripts.ml_training.essay_scoring.config import DatasetKind, ExperimentConfig, OffloadBackend
from scripts.ml_training.essay_scoring.cv_shared import SplitScheme

DEFAULT_DROP3_HANDCRAFTED: list[str] = ["has_conclusion", "clause_count", "flesch_kincaid"]


def load_config(config_path: Path | None) -> ExperimentConfig:
    """Load experiment config from JSON or return defaults."""

    if config_path is None:
        return ExperimentConfig()
    json_text = config_path.read_text(encoding="utf-8")
    return ExperimentConfig.from_json(json_text)


def apply_overrides(
    *,
    config: ExperimentConfig,
    dataset_kind: DatasetKind | None,
    dataset_path: Path | None,
    ellipse_train_path: Path | None,
    ellipse_test_path: Path | None,
    run_name: str | None,
    backend: OffloadBackend,
    offload_service_url: str | None,
    offload_request_timeout_s: float | None,
    embedding_service_url: str | None,
    language_tool_service_url: str | None,
) -> ExperimentConfig:
    """Apply CLI overrides to an `ExperimentConfig` instance."""

    if dataset_kind is not None:
        config = config.model_copy(update={"dataset_kind": dataset_kind})
    if dataset_path is not None:
        config = config.model_copy(update={"dataset_path": dataset_path})
    if ellipse_train_path is not None:
        config = config.model_copy(update={"ellipse_train_path": ellipse_train_path})
    if ellipse_test_path is not None:
        config = config.model_copy(update={"ellipse_test_path": ellipse_test_path})
    if run_name is not None:
        updated_output = config.output.model_copy(update={"run_name": run_name})
        config = config.model_copy(update={"output": updated_output})

    if backend == OffloadBackend.HEMMA and (embedding_service_url or language_tool_service_url):
        raise typer.BadParameter(
            "backend=hemma does not allow embedding_service_url/language_tool_service_url. "
            "Use --offload-service-url only (single-tunnel mode)."
        )

    request_timeout_s = (
        offload_request_timeout_s
        if offload_request_timeout_s is not None
        else config.offload.request_timeout_s
    )
    updated_offload = config.offload.model_copy(
        update={
            "backend": backend,
            "request_timeout_s": request_timeout_s,
            "offload_service_url": offload_service_url or config.offload.offload_service_url,
            "embedding_service_url": (embedding_service_url or config.offload.embedding_service_url)
            if backend != OffloadBackend.HEMMA
            else None,
            "language_tool_service_url": (
                language_tool_service_url or config.offload.language_tool_service_url
            )
            if backend != OffloadBackend.HEMMA
            else None,
        }
    )
    return config.model_copy(update={"offload": updated_offload})


def resolve_predictor_filters(
    *,
    predictor_handcrafted_keep: list[str] | None,
    predictor_handcrafted_drop: list[str] | None,
) -> tuple[list[str] | None, list[str] | None]:
    """Validate predictor filter flags and apply default drop-3 behavior."""

    if predictor_handcrafted_keep and predictor_handcrafted_drop:
        raise typer.BadParameter(
            "Cannot combine --predictor-handcrafted-keep with --predictor-handcrafted-drop."
        )
    if predictor_handcrafted_keep is None and predictor_handcrafted_drop is None:
        predictor_handcrafted_drop = list(DEFAULT_DROP3_HANDCRAFTED)
    return predictor_handcrafted_keep, predictor_handcrafted_drop


def resolve_split_scheme(*, scheme: str) -> SplitScheme:
    """Validate and normalize split scheme inputs used by command modules."""

    normalized = scheme.strip().lower()
    if normalized == "stratified_text":
        return "stratified_text"
    if normalized == "prompt_holdout":
        return "prompt_holdout"
    raise typer.BadParameter(
        "Invalid split scheme. Expected one of: `stratified_text`, `prompt_holdout`."
    )
