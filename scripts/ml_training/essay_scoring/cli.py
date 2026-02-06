"""CLI entrypoint for the essay-scoring research pipeline.

Purpose:
    Provide a thin Typer app that delegates command ownership to dedicated
    command modules (SRP-oriented command boundaries).

Relationships:
    - Command implementations live under `commands/`.
    - Invoked by `pdm run essay-scoring-research`.
"""

from __future__ import annotations

import typer

from scripts.ml_training.essay_scoring.commands.comparison_commands import (
    register as register_comparison_commands,
)
from scripts.ml_training.essay_scoring.commands.cv_commands import register as register_cv_commands
from scripts.ml_training.essay_scoring.commands.dataset_commands import (
    register as register_dataset_commands,
)
from scripts.ml_training.essay_scoring.commands.experiment_commands import (
    register as register_experiment_commands,
)
from scripts.ml_training.essay_scoring.commands.g3_launch_commands import (
    register as register_g3_launch_commands,
)
from scripts.ml_training.essay_scoring.commands.sweep_commands import (
    register as register_sweep_commands,
)
from scripts.ml_training.essay_scoring.commands.transformer_commands import (
    register as register_transformer_commands,
)

app = typer.Typer(help="Whitebox essay scoring research pipeline")


def register_commands(application: typer.Typer) -> None:
    """Register all command groups for the essay scoring CLI."""

    register_experiment_commands(application)
    register_dataset_commands(application)
    register_cv_commands(application)
    register_sweep_commands(application)
    register_comparison_commands(application)
    register_transformer_commands(application)
    register_g3_launch_commands(application)


register_commands(app)


if __name__ == "__main__":
    app()
