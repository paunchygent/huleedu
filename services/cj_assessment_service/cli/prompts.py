"""Prompt management commands."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, TypeAlias

import typer

from services.cj_assessment_service.cli.utils import JSONValue, make_admin_request

prompts_app = typer.Typer(help="Manage student prompts for assignments")

JSONMapping: TypeAlias = Mapping[str, JSONValue]


def upload_prompt_helper(assignment_id: str, content: str) -> str:
    """Upload student prompt and return storage_id."""

    payload: dict[str, JSONValue] = {
        "assignment_id": assignment_id,
        "prompt_text": content,
    }
    data = make_admin_request("POST", "/student-prompts", json_body=payload)

    if isinstance(data, dict):
        storage_id = data.get("student_prompt_storage_id")
        if isinstance(storage_id, str):
            return storage_id
        raise RuntimeError("student_prompt_storage_id not found in response")
    raise RuntimeError("Unexpected response format from prompt upload")


@prompts_app.command("upload")
def upload_prompt(
    assignment_id: str = typer.Option(..., help="Assignment ID for this prompt"),
    prompt_file: Path | None = typer.Option(None, help="Path to file containing the prompt"),
    prompt_text: str = typer.Option("", help="Inline prompt text when no file is given"),
) -> None:
    """Upload student prompt for an assignment (requires existing instruction)."""

    # XOR validation: exactly one of prompt_file or prompt_text must be provided
    if bool(prompt_file) == bool(prompt_text):
        typer.secho(
            "Provide exactly one of --prompt-file or --prompt-text",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    # Read from file if provided
    if prompt_file:
        if not prompt_file.exists():
            typer.secho(
                f"File not found: {prompt_file}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)
        try:
            content = prompt_file.read_text(encoding="utf-8")
        except Exception as e:
            typer.secho(
                f"Failed to read file: {e}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)
    else:
        content = prompt_text

    # Validate content is not empty
    if not content.strip():
        typer.secho(
            "Prompt content cannot be empty",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    # Reuse the helper
    try:
        storage_id = upload_prompt_helper(assignment_id, content)
    except RuntimeError as e:
        typer.secho(f"Upload failed: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # We need to reconstruct the response for display since the helper only returns ID
    # This is a slight regression in the CLI output compared to the original,
    # but the helper is designed for the instruction creation flow.
    # To match original output, we can just print the success message.

    typer.secho("Student prompt uploaded successfully", fg=typer.colors.GREEN)
    typer.echo(f"Assignment ID: {assignment_id}")
    typer.echo(f"Storage ID: {storage_id}")


@prompts_app.command("get")
def get_prompt(
    assignment_id: str = typer.Argument(..., help="Assignment ID to fetch prompt for"),
    output_file: Path | None = typer.Option(None, help="Optional file path to write prompt to"),
) -> None:
    """Fetch student prompt for an assignment."""

    # Fetch prompt via API
    data = make_admin_request("GET", f"/student-prompts/assignment/{assignment_id}")

    if not isinstance(data, dict):
        typer.secho("Unexpected response format", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Extract fields
    storage_id = data.get("student_prompt_storage_id", "N/A")
    grade_scale = data.get("grade_scale", "N/A")
    created_at = data.get("created_at", "N/A")
    prompt_text_value = data.get("prompt_text", "")

    # Validate prompt_text is a string
    if not isinstance(prompt_text_value, str):
        typer.secho("prompt_text field is not a string", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    prompt_text: str = prompt_text_value

    # Display metadata
    typer.secho("Student Prompt Details", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"Assignment ID: {assignment_id}")
    typer.echo(f"Storage ID: {storage_id}")
    typer.echo(f"Grade Scale: {grade_scale}")
    typer.echo(f"Created At: {created_at}")
    typer.echo("")

    # Handle output
    if output_file:
        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(prompt_text, encoding="utf-8")
            typer.secho(f"Prompt written to: {output_file}", fg=typer.colors.GREEN)
        except Exception as e:
            typer.secho(f"Failed to write file: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    else:
        typer.secho("Prompt Text:", fg=typer.colors.CYAN)
        typer.echo(prompt_text)
