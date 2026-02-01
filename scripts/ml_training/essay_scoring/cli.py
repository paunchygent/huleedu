"""CLI entrypoint for the essay scoring research pipeline."""

from __future__ import annotations

from pathlib import Path

import typer

from scripts.ml_training.essay_scoring.config import ExperimentConfig, FeatureSet
from scripts.ml_training.essay_scoring.logging_utils import configure_console_logging
from scripts.ml_training.essay_scoring.runner import run_ablation, run_experiment

app = typer.Typer(help="Whitebox essay scoring research pipeline")


@app.command("run")
def run_command(
    config_path: Path | None = typer.Option(
        None,
        help="Path to JSON config overrides",
    ),
    feature_set: FeatureSet | None = typer.Option(
        None,
        help="Feature set to train (handcrafted, embeddings, combined)",
    ),
    dataset_path: Path | None = typer.Option(
        None,
        help="Override dataset path",
    ),
    run_name: str | None = typer.Option(
        None,
        help="Optional run name suffix",
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
    """Run a single training + evaluation cycle."""

    configure_console_logging()
    config = _load_config(config_path)
    if dataset_path is not None:
        config = config.model_copy(update={"dataset_path": dataset_path})
    if run_name is not None:
        updated_output = config.output.model_copy(update={"run_name": run_name})
        config = config.model_copy(update={"output": updated_output})
    if embedding_service_url or language_tool_service_url:
        updated_offload = config.offload.model_copy(
            update={
                "embedding_service_url": (
                    embedding_service_url or config.offload.embedding_service_url
                ),
                "language_tool_service_url": language_tool_service_url
                or config.offload.language_tool_service_url,
            }
        )
        config = config.model_copy(update={"offload": updated_offload})

    summary = run_experiment(config, feature_set=feature_set)
    typer.echo(f"Run complete: {summary.run_paths.run_dir}")


@app.command("ablation")
def ablation_command(
    config_path: Path | None = typer.Option(
        None,
        help="Path to JSON config overrides",
    ),
    dataset_path: Path | None = typer.Option(
        None,
        help="Override dataset path",
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
    config = _load_config(config_path)
    if dataset_path is not None:
        config = config.model_copy(update={"dataset_path": dataset_path})
    if embedding_service_url or language_tool_service_url:
        updated_offload = config.offload.model_copy(
            update={
                "embedding_service_url": (
                    embedding_service_url or config.offload.embedding_service_url
                ),
                "language_tool_service_url": language_tool_service_url
                or config.offload.language_tool_service_url,
            }
        )
        config = config.model_copy(update={"offload": updated_offload})

    summaries = run_ablation(config)
    for summary in summaries:
        typer.echo(f"Ablation complete: {summary.feature_set.value} -> {summary.run_paths.run_dir}")


def _load_config(config_path: Path | None) -> ExperimentConfig:
    if config_path is None:
        return ExperimentConfig()
    json_text = config_path.read_text(encoding="utf-8")
    return ExperimentConfig.from_json(json_text)


if __name__ == "__main__":
    app()
