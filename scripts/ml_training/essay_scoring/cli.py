"""CLI entrypoint for the essay scoring research pipeline."""

from __future__ import annotations

from pathlib import Path

import typer

from scripts.ml_training.essay_scoring.config import (
    DatasetKind,
    ExperimentConfig,
    FeatureSet,
    OffloadBackend,
)
from scripts.ml_training.essay_scoring.cross_validation import run_cross_validation
from scripts.ml_training.essay_scoring.dataset_preparation import prepare_dataset
from scripts.ml_training.essay_scoring.drop_column_importance import run_drop_column_importance
from scripts.ml_training.essay_scoring.logging_utils import configure_console_logging
from scripts.ml_training.essay_scoring.runner import (
    featurize_experiment,
    run_ablation,
    run_experiment,
)
from scripts.ml_training.essay_scoring.split_definitions import generate_splits

app = typer.Typer(help="Whitebox essay scoring research pipeline")


@app.command("run")
def run_command(
    config_path: Path | None = typer.Option(
        None,
        help="Path to JSON config overrides",
    ),
    dataset_kind: DatasetKind | None = typer.Option(
        None,
        help="Dataset kind to load (ielts, ellipse).",
    ),
    feature_set: FeatureSet | None = typer.Option(
        None,
        help="Feature set to train (handcrafted, embeddings, combined)",
    ),
    dataset_path: Path | None = typer.Option(
        None,
        help="Override dataset path",
    ),
    ellipse_train_path: Path | None = typer.Option(
        None,
        help="Override ELLIPSE train CSV path (only used when --dataset-kind=ellipse).",
    ),
    ellipse_test_path: Path | None = typer.Option(
        None,
        help="Override ELLIPSE test CSV path (only used when --dataset-kind=ellipse).",
    ),
    run_name: str | None = typer.Option(
        None,
        help="Optional run name suffix",
    ),
    backend: OffloadBackend = typer.Option(
        OffloadBackend.LOCAL,
        help="Feature extraction backend (local or hemma).",
    ),
    offload_service_url: str | None = typer.Option(
        None,
        help="Combined offload service base URL (Hemma tunnel), e.g. http://127.0.0.1:19000.",
    ),
    offload_request_timeout_s: float | None = typer.Option(
        None,
        help=(
            "Offload request timeout in seconds (applies to Hemma /v1/extract calls). "
            "If omitted, uses the config default (typically 60s)."
        ),
        min=1.0,
        max=600.0,
    ),
    embedding_service_url: str | None = typer.Option(
        None,
        help="Optional Hemma embedding offload base URL (e.g. http://127.0.0.1:19000).",
    ),
    language_tool_service_url: str | None = typer.Option(
        None,
        help="Optional Hemma LanguageTool service base URL (e.g. http://127.0.0.1:18085).",
    ),
    reuse_feature_store_dir: Path | None = typer.Option(
        None,
        help="Reuse a previously generated feature store directory (or its parent run dir).",
    ),
    skip_shap: bool = typer.Option(
        False,
        help="Skip SHAP artifact generation (useful for fast sweeps).",
    ),
    skip_grade_scale_report: bool = typer.Option(
        False,
        help="Skip grade-scale report generation (useful for fast sweeps).",
    ),
) -> None:
    """Run a single training + evaluation cycle."""

    configure_console_logging()
    config = _apply_overrides(
        config=_load_config(config_path),
        dataset_kind=dataset_kind,
        dataset_path=dataset_path,
        ellipse_train_path=ellipse_train_path,
        ellipse_test_path=ellipse_test_path,
        run_name=run_name,
        backend=backend,
        offload_service_url=offload_service_url,
        offload_request_timeout_s=offload_request_timeout_s,
        embedding_service_url=embedding_service_url,
        language_tool_service_url=language_tool_service_url,
    )
    summary = run_experiment(
        config,
        feature_set=feature_set,
        reuse_feature_store_dir=reuse_feature_store_dir,
        skip_shap=skip_shap,
        skip_grade_scale_report=skip_grade_scale_report,
    )
    typer.echo(f"Run complete: {summary.run_paths.run_dir}")


@app.command("featurize")
def featurize_command(
    config_path: Path | None = typer.Option(
        None,
        help="Path to JSON config overrides",
    ),
    dataset_kind: DatasetKind | None = typer.Option(
        None,
        help="Dataset kind to load (ielts, ellipse).",
    ),
    feature_set: FeatureSet | None = typer.Option(
        None,
        help="Feature set to featurize (handcrafted, embeddings, combined)",
    ),
    dataset_path: Path | None = typer.Option(
        None,
        help="Override dataset path",
    ),
    ellipse_train_path: Path | None = typer.Option(
        None,
        help="Override ELLIPSE train CSV path (only used when --dataset-kind=ellipse).",
    ),
    ellipse_test_path: Path | None = typer.Option(
        None,
        help="Override ELLIPSE test CSV path (only used when --dataset-kind=ellipse).",
    ),
    run_name: str | None = typer.Option(
        None,
        help="Optional run name suffix",
    ),
    backend: OffloadBackend = typer.Option(
        OffloadBackend.LOCAL,
        help="Feature extraction backend (local or hemma).",
    ),
    offload_service_url: str | None = typer.Option(
        None,
        help="Combined offload service base URL (Hemma tunnel), e.g. http://127.0.0.1:19000.",
    ),
    offload_request_timeout_s: float | None = typer.Option(
        None,
        help=(
            "Offload request timeout in seconds (applies to Hemma /v1/extract calls). "
            "If omitted, uses the config default (typically 60s)."
        ),
        min=1.0,
        max=600.0,
    ),
    embedding_service_url: str | None = typer.Option(
        None,
        help="Optional Hemma embedding offload base URL (e.g. http://127.0.0.1:19000).",
    ),
    language_tool_service_url: str | None = typer.Option(
        None,
        help="Optional Hemma LanguageTool service base URL (e.g. http://127.0.0.1:18085).",
    ),
) -> None:
    """Extract and persist features for warm-cache experimentation."""

    configure_console_logging()
    config = _apply_overrides(
        config=_load_config(config_path),
        dataset_kind=dataset_kind,
        dataset_path=dataset_path,
        ellipse_train_path=ellipse_train_path,
        ellipse_test_path=ellipse_test_path,
        run_name=run_name,
        backend=backend,
        offload_service_url=offload_service_url,
        offload_request_timeout_s=offload_request_timeout_s,
        embedding_service_url=embedding_service_url,
        language_tool_service_url=language_tool_service_url,
    )
    summary = featurize_experiment(config, feature_set=feature_set)
    typer.echo(f"Featurize complete: {summary.feature_store_dir}")


@app.command("ablation")
def ablation_command(
    config_path: Path | None = typer.Option(
        None,
        help="Path to JSON config overrides",
    ),
    dataset_kind: DatasetKind | None = typer.Option(
        None,
        help="Dataset kind to load (ielts, ellipse).",
    ),
    dataset_path: Path | None = typer.Option(
        None,
        help="Override dataset path",
    ),
    ellipse_train_path: Path | None = typer.Option(
        None,
        help="Override ELLIPSE train CSV path (only used when --dataset-kind=ellipse).",
    ),
    ellipse_test_path: Path | None = typer.Option(
        None,
        help="Override ELLIPSE test CSV path (only used when --dataset-kind=ellipse).",
    ),
    backend: OffloadBackend = typer.Option(
        OffloadBackend.LOCAL,
        help="Feature extraction backend (local or hemma).",
    ),
    offload_service_url: str | None = typer.Option(
        None,
        help="Combined offload service base URL (Hemma tunnel), e.g. http://127.0.0.1:19000.",
    ),
    offload_request_timeout_s: float | None = typer.Option(
        None,
        help=(
            "Offload request timeout in seconds (applies to Hemma /v1/extract calls). "
            "If omitted, uses the config default (typically 60s)."
        ),
        min=1.0,
        max=600.0,
    ),
    embedding_service_url: str | None = typer.Option(
        None,
        help="Optional Hemma embedding offload base URL (e.g. http://127.0.0.1:19000).",
    ),
    language_tool_service_url: str | None = typer.Option(
        None,
        help="Optional Hemma LanguageTool service base URL (e.g. http://127.0.0.1:18085).",
    ),
) -> None:
    """Run ablation experiments across feature sets."""

    configure_console_logging()
    config = _apply_overrides(
        config=_load_config(config_path),
        dataset_kind=dataset_kind,
        dataset_path=dataset_path,
        ellipse_train_path=ellipse_train_path,
        ellipse_test_path=ellipse_test_path,
        run_name=None,
        backend=backend,
        offload_service_url=offload_service_url,
        offload_request_timeout_s=offload_request_timeout_s,
        embedding_service_url=embedding_service_url,
        language_tool_service_url=language_tool_service_url,
    )

    summaries = run_ablation(config)
    for summary in summaries:
        typer.echo(f"Ablation complete: {summary.feature_set.value} -> {summary.run_paths.run_dir}")


@app.command("prepare-dataset")
def prepare_dataset_command(
    config_path: Path | None = typer.Option(
        None,
        help="Path to JSON config overrides",
    ),
    dataset_kind: DatasetKind | None = typer.Option(
        None,
        help="Dataset kind to load (ielts, ellipse).",
    ),
    ellipse_train_path: Path | None = typer.Option(
        None,
        help="Override ELLIPSE train CSV path (only used when --dataset-kind=ellipse).",
    ),
    ellipse_test_path: Path | None = typer.Option(
        None,
        help="Override ELLIPSE test CSV path (only used when --dataset-kind=ellipse).",
    ),
    run_name: str | None = typer.Option(
        None,
        help="Optional run name suffix",
    ),
    min_words: int = typer.Option(
        200,
        help="Minimum word count (inclusive).",
        min=0,
    ),
    max_words: int = typer.Option(
        1000,
        help="Maximum word count (inclusive).",
        min=0,
    ),
) -> None:
    """Prepare dataset artifacts + integrity report for stable experimentation."""

    configure_console_logging()
    config = _apply_overrides(
        config=_load_config(config_path),
        dataset_kind=dataset_kind,
        dataset_path=None,
        ellipse_train_path=ellipse_train_path,
        ellipse_test_path=ellipse_test_path,
        run_name=run_name,
        backend=OffloadBackend.LOCAL,
        offload_service_url=None,
        offload_request_timeout_s=None,
        embedding_service_url=None,
        language_tool_service_url=None,
    )
    summary = prepare_dataset(config, min_words=min_words, max_words=max_words)
    typer.echo(f"Prepared dataset: {summary.prepared_train_path}")
    typer.echo(f"Prepared dataset: {summary.prepared_test_path}")
    typer.echo(f"Report: {summary.report_path}")


@app.command("make-splits")
def make_splits_command(
    config_path: Path | None = typer.Option(
        None,
        help="Path to JSON config overrides",
    ),
    dataset_kind: DatasetKind | None = typer.Option(
        None,
        help="Dataset kind to load (ielts, ellipse).",
    ),
    ellipse_train_path: Path | None = typer.Option(
        None,
        help="Override ELLIPSE train CSV path (only used when --dataset-kind=ellipse).",
    ),
    ellipse_test_path: Path | None = typer.Option(
        None,
        help="Override ELLIPSE test CSV path (only used when --dataset-kind=ellipse).",
    ),
    run_name: str | None = typer.Option(
        None,
        help="Optional run name suffix",
    ),
    min_words: int = typer.Option(
        200,
        help="Minimum word count (inclusive).",
        min=0,
    ),
    max_words: int = typer.Option(
        1000,
        help="Maximum word count (inclusive).",
        min=0,
    ),
    n_splits: int = typer.Option(
        5,
        help="Number of cross-validation folds to generate.",
        min=2,
        max=20,
    ),
) -> None:
    """Generate reusable split definitions (CV + prompt holdout)."""

    configure_console_logging()
    config = _apply_overrides(
        config=_load_config(config_path),
        dataset_kind=dataset_kind,
        dataset_path=None,
        ellipse_train_path=ellipse_train_path,
        ellipse_test_path=ellipse_test_path,
        run_name=run_name,
        backend=OffloadBackend.LOCAL,
        offload_service_url=None,
        offload_request_timeout_s=None,
        embedding_service_url=None,
        language_tool_service_url=None,
    )
    summary = generate_splits(config, min_words=min_words, max_words=max_words, n_splits=n_splits)
    typer.echo(f"Splits: {summary.splits_path}")
    typer.echo(f"Report: {summary.report_path}")


@app.command("cv")
def cv_command(
    splits_path: Path = typer.Option(
        ...,
        help="Path to a splits.json file created by `make-splits`.",
        exists=True,
        dir_okay=False,
        file_okay=True,
    ),
    scheme: str = typer.Option(
        "stratified_text",
        help="Split scheme: stratified_text or prompt_holdout.",
    ),
    config_path: Path | None = typer.Option(
        None,
        help="Path to JSON config overrides",
    ),
    dataset_kind: DatasetKind | None = typer.Option(
        None,
        help="Dataset kind to load (ielts, ellipse).",
    ),
    feature_set: FeatureSet | None = typer.Option(
        None,
        help="Feature set to train (handcrafted, embeddings, combined)",
    ),
    ellipse_train_path: Path | None = typer.Option(
        None,
        help="Override ELLIPSE train CSV path (only used when --dataset-kind=ellipse).",
    ),
    ellipse_test_path: Path | None = typer.Option(
        None,
        help="Override ELLIPSE test CSV path (only used when --dataset-kind=ellipse).",
    ),
    run_name: str | None = typer.Option(
        None,
        help="Optional run name suffix",
    ),
    backend: OffloadBackend = typer.Option(
        OffloadBackend.LOCAL,
        help="Feature extraction backend (local or hemma).",
    ),
    offload_service_url: str | None = typer.Option(
        None,
        help="Combined offload service base URL (Hemma tunnel), e.g. http://127.0.0.1:19000.",
    ),
    offload_request_timeout_s: float | None = typer.Option(
        None,
        help=(
            "Offload request timeout in seconds (applies to Hemma /v1/extract calls). "
            "If omitted, uses the config default (typically 60s)."
        ),
        min=1.0,
        max=600.0,
    ),
    embedding_service_url: str | None = typer.Option(
        None,
        help="Optional Hemma embedding offload base URL (e.g. http://127.0.0.1:19000).",
    ),
    language_tool_service_url: str | None = typer.Option(
        None,
        help="Optional Hemma LanguageTool service base URL (e.g. http://127.0.0.1:18085).",
    ),
    reuse_cv_feature_store_dir: Path | None = typer.Option(
        None,
        help="Reuse a previously generated CV feature store directory (or its parent run dir).",
    ),
    min_words: int | None = typer.Option(
        None,
        help="Optional override for min_words; must match the splits.json window if set.",
        min=0,
    ),
    max_words: int | None = typer.Option(
        None,
        help="Optional override for max_words; must match the splits.json window if set.",
        min=0,
    ),
) -> None:
    """Run cross-validation using a pre-generated splits.json definition."""

    configure_console_logging()
    config = _apply_overrides(
        config=_load_config(config_path),
        dataset_kind=dataset_kind,
        dataset_path=None,
        ellipse_train_path=ellipse_train_path,
        ellipse_test_path=ellipse_test_path,
        run_name=run_name,
        backend=backend,
        offload_service_url=offload_service_url,
        offload_request_timeout_s=offload_request_timeout_s,
        embedding_service_url=embedding_service_url,
        language_tool_service_url=language_tool_service_url,
    )
    summary = run_cross_validation(
        config,
        feature_set=feature_set or config.feature_set,
        splits_path=splits_path,
        scheme=scheme,  # type: ignore[arg-type]
        reuse_cv_feature_store_dir=reuse_cv_feature_store_dir,
        min_words=min_words,
        max_words=max_words,
    )
    typer.echo(f"CV complete: {summary.run_paths.run_dir}")
    typer.echo(f"Metrics: {summary.metrics_path}")
    typer.echo(f"Report: {summary.report_path}")


@app.command("drop-column")
def drop_column_command(
    splits_path: Path = typer.Option(
        ...,
        help="Path to a splits.json file created by `make-splits`.",
        exists=True,
        dir_okay=False,
        file_okay=True,
    ),
    scheme: str = typer.Option(
        "stratified_text",
        help="Split scheme: stratified_text or prompt_holdout.",
    ),
    config_path: Path | None = typer.Option(
        None,
        help="Path to JSON config overrides",
    ),
    dataset_kind: DatasetKind | None = typer.Option(
        None,
        help="Dataset kind to load (ielts, ellipse).",
    ),
    feature_set: FeatureSet | None = typer.Option(
        None,
        help="Feature set to train (handcrafted, embeddings, combined)",
    ),
    ellipse_train_path: Path | None = typer.Option(
        None,
        help="Override ELLIPSE train CSV path (only used when --dataset-kind=ellipse).",
    ),
    ellipse_test_path: Path | None = typer.Option(
        None,
        help="Override ELLIPSE test CSV path (only used when --dataset-kind=ellipse).",
    ),
    run_name: str | None = typer.Option(
        None,
        help="Optional run name suffix",
    ),
    backend: OffloadBackend = typer.Option(
        OffloadBackend.LOCAL,
        help="Feature extraction backend (local or hemma).",
    ),
    offload_service_url: str | None = typer.Option(
        None,
        help="Combined offload service base URL (Hemma tunnel), e.g. http://127.0.0.1:19000.",
    ),
    offload_request_timeout_s: float | None = typer.Option(
        None,
        help=(
            "Offload request timeout in seconds (applies to Hemma /v1/extract calls). "
            "If omitted, uses the config default (typically 60s)."
        ),
        min=1.0,
        max=600.0,
    ),
    embedding_service_url: str | None = typer.Option(
        None,
        help="Optional Hemma embedding offload base URL (e.g. http://127.0.0.1:19000).",
    ),
    language_tool_service_url: str | None = typer.Option(
        None,
        help="Optional Hemma LanguageTool service base URL (e.g. http://127.0.0.1:18085).",
    ),
    reuse_cv_feature_store_dir: Path | None = typer.Option(
        None,
        help="Reuse a previously generated CV feature store directory (or its parent run dir).",
    ),
    min_words: int | None = typer.Option(
        None,
        help="Optional override for min_words; must match the splits.json window if set.",
        min=0,
    ),
    max_words: int | None = typer.Option(
        None,
        help="Optional override for max_words; must match the splits.json window if set.",
        min=0,
    ),
) -> None:
    """Run CV drop-column importance for handcrafted features."""

    configure_console_logging()
    config = _apply_overrides(
        config=_load_config(config_path),
        dataset_kind=dataset_kind,
        dataset_path=None,
        ellipse_train_path=ellipse_train_path,
        ellipse_test_path=ellipse_test_path,
        run_name=run_name,
        backend=backend,
        offload_service_url=offload_service_url,
        offload_request_timeout_s=offload_request_timeout_s,
        embedding_service_url=embedding_service_url,
        language_tool_service_url=language_tool_service_url,
    )
    summary = run_drop_column_importance(
        config,
        feature_set=feature_set or config.feature_set,
        splits_path=splits_path,
        scheme=scheme,  # type: ignore[arg-type]
        reuse_cv_feature_store_dir=reuse_cv_feature_store_dir,
        min_words=min_words,
        max_words=max_words,
    )
    typer.echo(f"Drop-column complete: {summary.run_paths.run_dir}")
    typer.echo(f"Metrics: {summary.metrics_path}")
    typer.echo(f"Report: {summary.report_path}")


def _load_config(config_path: Path | None) -> ExperimentConfig:
    if config_path is None:
        return ExperimentConfig()
    json_text = config_path.read_text(encoding="utf-8")
    return ExperimentConfig.from_json(json_text)


def _apply_overrides(
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

    if offload_request_timeout_s is not None:
        request_timeout_s = offload_request_timeout_s
    else:
        request_timeout_s = config.offload.request_timeout_s

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
    config = config.model_copy(update={"offload": updated_offload})
    return config


if __name__ == "__main__":
    app()
