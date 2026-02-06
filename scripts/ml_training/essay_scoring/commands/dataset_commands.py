"""Dataset preparation and split-definition command registrations.

Purpose:
    Host commands that create canonical prepared datasets and reusable
    split definitions for downstream CV workflows.

Relationships:
    - Registered by `scripts.ml_training.essay_scoring.cli`.
    - Uses dataset/split services from `dataset_preparation` and
      `split_definitions`.
"""

from __future__ import annotations

from pathlib import Path

import typer

from scripts.ml_training.essay_scoring.commands.common import apply_overrides, load_config
from scripts.ml_training.essay_scoring.config import DatasetKind, OffloadBackend
from scripts.ml_training.essay_scoring.dataset_preparation import prepare_dataset
from scripts.ml_training.essay_scoring.logging_utils import configure_console_logging
from scripts.ml_training.essay_scoring.split_definitions import generate_splits


def register(app: typer.Typer) -> None:
    """Register dataset and split definition commands on the app."""

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
        config = apply_overrides(
            config=load_config(config_path),
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
        config = apply_overrides(
            config=load_config(config_path),
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
        summary = generate_splits(
            config,
            min_words=min_words,
            max_words=max_words,
            n_splits=n_splits,
        )
        typer.echo(f"Splits: {summary.splits_path}")
        typer.echo(f"Report: {summary.report_path}")
