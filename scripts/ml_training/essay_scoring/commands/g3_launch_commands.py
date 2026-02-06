"""Gate G3 Hemma launcher command registrations.

Purpose:
    Register one canonical command that performs strict Hemma preflight and
    detached launch for transformer Gate G3 runs.

Relationships:
    - Registered by `scripts.ml_training.essay_scoring.cli`.
    - Delegates orchestration to `scripts.ml_training.essay_scoring.g3_launch_hemma`.
"""

from __future__ import annotations

import typer

from scripts.ml_training.essay_scoring.g3_launch_hemma import (
    DEFAULT_REMOTE_HOST,
    DEFAULT_REMOTE_REPO_ROOT,
    DEFAULT_RUN_NAME_PREFIX,
    G3LaunchConfig,
    G3LaunchError,
    run_g3_launch,
)
from scripts.ml_training.essay_scoring.logging_utils import configure_console_logging


def register(app: typer.Typer) -> None:
    """Register Gate G3 Hemma launcher command on the provided app."""

    @app.command("g3-launch-hemma")
    def g3_launch_hemma_command(
        remote_host: str = typer.Option(
            DEFAULT_REMOTE_HOST,
            help="SSH host alias for Hemma.",
        ),
        remote_repo_root: str = typer.Option(
            DEFAULT_REMOTE_REPO_ROOT,
            help=(
                "Canonical HuleEdu repo root on Hemma (AGENTS.md: /home/paunchygent/apps/huleedu)."
            ),
        ),
        run_name_prefix: str = typer.Option(
            DEFAULT_RUN_NAME_PREFIX,
            help="Run-name prefix used before timestamp suffix.",
        ),
        dry_run: bool = typer.Option(
            False,
            help="Print generated preflight/launch scripts without executing.",
        ),
    ) -> None:
        """Run strict preflight and detached Gate G3 launch on Hemma."""

        configure_console_logging()
        config = G3LaunchConfig(
            remote_host=remote_host,
            remote_repo_root=remote_repo_root,
            run_name_prefix=run_name_prefix,
        )
        if dry_run:
            from scripts.ml_training.essay_scoring.g3_launch_hemma import (
                build_launch_script,
                build_preflight_script,
            )

            typer.echo("# PREFLIGHT SCRIPT")
            typer.echo(build_preflight_script(config=config))
            typer.echo("")
            typer.echo("# LAUNCH SCRIPT")
            typer.echo(build_launch_script(config=config))
            raise typer.Exit(code=0)

        try:
            result = run_g3_launch(config=config)
        except G3LaunchError as exc:
            raise typer.BadParameter(str(exc)) from exc

        typer.echo(f"Gate G3 launch started: {result.run_name}")
        typer.echo(f"Driver log: {result.driver_log}")
