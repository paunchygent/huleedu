"""Instruction management commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, TypeAlias

import typer

from services.cj_assessment_service.cli.prompts import upload_prompt_helper
from services.cj_assessment_service.cli.utils import JSONValue, make_admin_request

instructions_app = typer.Typer(help="Manage assessment instructions")

JSONMapping: TypeAlias = Mapping[str, JSONValue]


@instructions_app.command("create")
def create_instruction(
    assignment_id: str = typer.Option("", help="Assignment ID (mutually exclusive with course)"),
    course_id: str = typer.Option("", help="Course ID when assignment ID is not provided"),
    instructions_file: Path | None = typer.Option(
        None, help="Path to a markdown/text file containing the instructions"
    ),
    instructions_text: str = typer.Option(
        "", help="Inline instructions text when no file is given"
    ),
    grade_scale: str = typer.Option(..., help="Registered grade scale ID"),
    prompt_file: Path | None = typer.Option(
        None, help="Optional path to file containing student prompt"
    ),
    prompt_text: str = typer.Option("", help="Optional inline student prompt text"),
) -> None:
    """Create or update assessment instructions with optional student prompt."""

    # Validate assignment_id/course_id mutual exclusivity
    if bool(assignment_id) == bool(course_id):
        typer.secho("Provide exactly one of --assignment-id or --course-id", fg=typer.colors.RED)
        raise typer.Exit(code=2)

    # Validate prompt_file/prompt_text mutual exclusivity (both can be absent)
    if prompt_file and prompt_text:
        typer.secho(
            "Provide at most one of --prompt-file or --prompt-text",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    # Load instructions
    if instructions_file:
        instructions = instructions_file.read_text(encoding="utf-8")
    elif instructions_text:
        instructions = instructions_text
    else:
        instructions = typer.prompt("Instructions text")

    # Upload prompt if provided (only for assignment-level instructions)
    student_prompt_storage_id: str | None = None
    if prompt_file or prompt_text:
        if not assignment_id:
            typer.secho(
                "Student prompt can only be uploaded with --assignment-id",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)

        # Read prompt content
        if prompt_file:
            if not prompt_file.exists():
                typer.secho(
                    f"Prompt file not found: {prompt_file}",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(code=1)
            try:
                prompt_content = prompt_file.read_text(encoding="utf-8")
            except Exception as e:
                typer.secho(
                    f"Failed to read prompt file: {e}",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(code=1)
        else:
            prompt_content = prompt_text

        # Validate and upload
        if not prompt_content.strip():
            typer.secho(
                "Prompt content cannot be empty",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)

        student_prompt_storage_id = upload_prompt_helper(assignment_id, prompt_content)
        typer.secho(
            f"Student prompt uploaded (storage_id: {student_prompt_storage_id})",
            fg=typer.colors.GREEN,
        )

    # Create/update instruction
    payload: dict[str, JSONValue] = {
        "assignment_id": assignment_id or None,
        "course_id": course_id or None,
        "instructions_text": instructions,
        "grade_scale": grade_scale,
    }
    if student_prompt_storage_id:
        payload["student_prompt_storage_id"] = student_prompt_storage_id

    data = make_admin_request("POST", "/assessment-instructions", json_body=payload)
    typer.echo(json.dumps(data, indent=2))


@instructions_app.command("list")
def list_instructions(
    grade_scale: str = typer.Option(None, help="Filter by grade scale"),
    page: int = typer.Option(1, min=1),
    page_size: int = typer.Option(20, min=1, max=200),
) -> None:
    """List stored assessment instructions."""

    query = f"?page={page}&page_size={page_size}"
    if grade_scale:
        query += f"&grade_scale={grade_scale}"
    data = make_admin_request("GET", f"/assessment-instructions{query}")
    typer.echo(json.dumps(data, indent=2))


@instructions_app.command("delete")
def delete_instruction(
    assignment_id: str = typer.Option("", help="Assignment ID to delete"),
    course_id: str = typer.Option("", help="Course ID when deleting fallback instructions"),
) -> None:
    """Delete assessment instructions."""

    if bool(assignment_id) == bool(course_id):
        typer.secho("Provide exactly one of --assignment-id or --course-id", fg=typer.colors.RED)
        raise typer.Exit(code=2)

    if assignment_id:
        path = f"/assessment-instructions/assignment/{assignment_id}"
    else:
        path = f"/assessment-instructions/course/{course_id}"

    make_admin_request("DELETE", path)
    typer.secho("Instruction deleted", fg=typer.colors.GREEN)


@instructions_app.command("get")
def get_instruction(
    assignment_id: str = typer.Argument(..., help="Assignment ID to fetch"),
) -> None:
    """Retrieve instructions for a specific assignment."""

    data = make_admin_request(
        "GET",
        f"/assessment-instructions/assignment/{assignment_id}",
    )
    typer.echo(json.dumps(data, indent=2))
