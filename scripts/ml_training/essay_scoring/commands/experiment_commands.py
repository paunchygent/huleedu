"""Run/featurize/ablation command registrations.

Purpose:
    Host experiment execution commands that operate on a single dataset/config
    without split-definition orchestration.

Relationships:
    - Registered by `scripts.ml_training.essay_scoring.cli`.
    - Uses runner functions from `scripts.ml_training.essay_scoring.runner`.
"""

from __future__ import annotations

from pathlib import Path

import typer

from scripts.ml_training.essay_scoring.commands.common import apply_overrides, load_config
from scripts.ml_training.essay_scoring.config import DatasetKind, FeatureSet, OffloadBackend
from scripts.ml_training.essay_scoring.logging_utils import configure_console_logging
from scripts.ml_training.essay_scoring.runner import (
    featurize_experiment,
    run_ablation,
    run_experiment,
)


def register(app: typer.Typer) -> None:
    """Register experiment execution commands on the provided app."""

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
        config = apply_overrides(
            config=load_config(config_path),
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
        config = apply_overrides(
            config=load_config(config_path),
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
        config = apply_overrides(
            config=load_config(config_path),
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
            typer.echo(
                f"Ablation complete: {summary.feature_set.value} -> {summary.run_paths.run_dir}"
            )
