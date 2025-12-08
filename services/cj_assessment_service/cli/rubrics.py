"""Rubric management commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, TypeAlias

import typer

from services.cj_assessment_service.cli.utils import JSONValue, make_admin_request

rubrics_app = typer.Typer(help="Manage judge rubrics for assignments")

JSONMapping: TypeAlias = Mapping[str, JSONValue]


@rubrics_app.command("upload")
def upload_rubric(
    assignment_id: str = typer.Option(..., help="Assignment ID for this rubric"),
    rubric_file: Path | None = typer.Option(None, help="Path to file containing the rubric"),
    rubric_text: str = typer.Option("", help="Inline rubric text when no file is given"),
) -> None:
    """Upload judge rubric for an assignment (requires existing instruction)."""

    # XOR validation: exactly one of rubric_file or rubric_text must be provided
    if bool(rubric_file) == bool(rubric_text):
        typer.secho(
            "Provide exactly one of --rubric-file or --rubric-text",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    # Read from file if provided
    if rubric_file:
        if not rubric_file.exists():
            typer.secho(
                f"File not found: {rubric_file}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)
        try:
            content = rubric_file.read_text(encoding="utf-8")
        except Exception as e:
            typer.secho(
                f"Failed to read file: {e}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)
    else:
        content = rubric_text

    # Validate content is not empty
    if not content.strip():
        typer.secho(
            "Rubric content cannot be empty",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    # Upload rubric via API
    payload: dict[str, JSONValue] = {
        "assignment_id": assignment_id,
        "rubric_text": content,
    }
    data = make_admin_request("POST", "/judge-rubrics", json_body=payload)

    # Extract and display key information
    if isinstance(data, dict):
        storage_id = data.get("judge_rubric_storage_id", "unknown")
        typer.secho("Judge rubric uploaded successfully", fg=typer.colors.GREEN)
        typer.echo(f"Assignment ID: {assignment_id}")
        typer.echo(f"Storage ID: {storage_id}")
        typer.echo("")
        typer.echo(json.dumps(data, indent=2))
    else:
        typer.secho("Upload succeeded but response format unexpected", fg=typer.colors.YELLOW)
        typer.echo(json.dumps(data, indent=2))


@rubrics_app.command("get")
def get_rubric(
    assignment_id: str = typer.Argument(..., help="Assignment ID to fetch rubric for"),
    output_file: Path | None = typer.Option(None, help="Write rubric content to file"),
) -> None:
    """Fetch judge rubric for an assignment."""

    data = make_admin_request("GET", f"/judge-rubrics/assignment/{assignment_id}")

    if not isinstance(data, dict):
        typer.secho("Unexpected response format", fg=typer.colors.RED, err=True)
        typer.echo(json.dumps(data, indent=2))
        raise typer.Exit(code=1)

    # Extract fields with type-safe coercion
    raw_rubric_text = data.get("rubric_text", "")
    rubric_text = (
        raw_rubric_text if isinstance(raw_rubric_text, str) else str(raw_rubric_text or "")
    )
    storage_id = data.get("judge_rubric_storage_id", "unknown")
    grade_scale = data.get("grade_scale", "unknown")
    created_at = data.get("created_at", "unknown")

    # Display metadata
    typer.secho(f"Judge Rubric for {assignment_id}", fg=typer.colors.GREEN)
    typer.echo(f"Storage ID: {storage_id}")
    typer.echo(f"Grade Scale: {grade_scale}")
    typer.echo(f"Created At: {created_at}")
    typer.echo("")

    # Handle output
    if output_file:
        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(rubric_text, encoding="utf-8")
            typer.secho(f"Rubric written to: {output_file}", fg=typer.colors.GREEN)
        except Exception as e:
            typer.secho(f"Failed to write file: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    else:
        typer.secho("Rubric Text:", fg=typer.colors.CYAN)
        typer.echo(rubric_text)
