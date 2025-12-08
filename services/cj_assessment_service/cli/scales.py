"""Grade scale inspection commands."""

from __future__ import annotations

import typer
from common_core.grade_scales import GRADE_SCALES

scales_app = typer.Typer(help="Inspect registered grade scales")


@scales_app.command("list")
def list_scales() -> None:
    """Print registered grade scales."""

    for scale_id, metadata in GRADE_SCALES.items():
        typer.echo(f"{scale_id}: {metadata.display_name} ({len(metadata.grades)} grades)")
