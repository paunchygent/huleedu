"""Typer-based admin helper for CJ assessment service."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Mapping, TypeAlias, TypedDict, cast

import httpx
import typer
from common_core.grade_scales import GRADE_SCALES

IDENTITY_BASE_URL = os.getenv("IDENTITY_BASE_URL", "http://localhost:7005/v1/auth")
CJ_ADMIN_BASE_URL = os.getenv("CJ_ADMIN_BASE_URL", "http://localhost:9095/admin/v1")
TOKEN_CACHE_PATH = Path(
    os.getenv("CJ_ADMIN_TOKEN_PATH", Path.home() / ".huleedu" / "cj_admin_token.json")
)
CJ_ADMIN_TOKEN_OVERRIDE = os.getenv("CJ_ADMIN_TOKEN")
CJ_ADMIN_EMAIL = os.getenv("CJ_ADMIN_EMAIL")
CJ_ADMIN_PASSWORD = os.getenv("CJ_ADMIN_PASSWORD")

app = typer.Typer(help="CJ Assessment admin CLI")
instructions_app = typer.Typer(help="Manage assessment instructions")
app.add_typer(instructions_app, name="instructions")
scales_app = typer.Typer(help="Inspect registered grade scales")
app.add_typer(scales_app, name="scales")
prompts_app = typer.Typer(help="Manage student prompts for assignments")
app.add_typer(prompts_app, name="prompts")
token_app = typer.Typer(help="Admin token utilities")
app.add_typer(token_app, name="token")

JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | dict[str, "JSONValue"] | list["JSONValue"]
JSONMapping: TypeAlias = Mapping[str, JSONValue]


class TokenCache(TypedDict, total=False):
    """Identity token payload cached locally."""

    access_token: str
    refresh_token: str
    expires_in: int
    expires_at: str


class AuthManager:
    """Handles Identity login/refresh and token caching."""

    def __init__(self) -> None:
        self.override_token = CJ_ADMIN_TOKEN_OVERRIDE

    def get_token(self) -> str:
        """Return a valid JWT, refreshing or prompting login when needed."""

        if self.override_token:
            return self.override_token

        cache = self._load_cache()
        if cache and not self._is_expired(cache):
            token = cache.get("access_token")
            if isinstance(token, str):
                return token

        if cache and cache.get("refresh_token"):
            refreshed = self._refresh(cache["refresh_token"])
            self._save_cache(refreshed)
            token = refreshed.get("access_token")
            if isinstance(token, str):
                return token

        typer.secho("No cached admin token found. Run `cj-admin login` first.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    def login(self, email: str, password: str) -> TokenCache:
        """Perform credentialed login via Identity service."""

        correlation_id = str(uuid.uuid4())
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{IDENTITY_BASE_URL}/login",
                json={"email": email, "password": password},
                headers={"X-Correlation-ID": correlation_id},
            )
        if resp.status_code != 200:
            typer.secho(
                f"Login failed ({resp.status_code}): {resp.text}", fg=typer.colors.RED, err=True
            )
            raise typer.Exit(code=1)

        data = resp.json()
        if not isinstance(data, dict):
            raise RuntimeError("Identity login response malformed")
        payload = cast(TokenCache, data)
        self._save_cache(payload)
        return payload

    def _refresh(self, refresh_token: str) -> TokenCache:
        correlation_id = str(uuid.uuid4())
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{IDENTITY_BASE_URL}/refresh",
                json={"refresh_token": refresh_token},
                headers={"X-Correlation-ID": correlation_id},
            )
        if resp.status_code != 200:
            typer.secho(
                "Refresh token invalid. Please run `cj-admin login` again.",
                fg=typer.colors.YELLOW,
            )
            raise typer.Exit(code=1)

        data = resp.json()
        if not isinstance(data, dict):
            raise RuntimeError("Identity refresh response malformed")
        return cast(TokenCache, data)

    def _is_expired(self, cache: TokenCache) -> bool:
        expires_at = cache.get("expires_at")
        if not expires_at:
            return True
        try:
            expiry = datetime.fromisoformat(expires_at)
        except ValueError:
            return True
        return datetime.now(UTC) >= expiry

    def _load_cache(self) -> TokenCache | None:
        if not TOKEN_CACHE_PATH.exists():
            return None
        try:
            data = json.loads(TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None

        if isinstance(data, dict):
            return cast(TokenCache, data)
        return None

    def _save_cache(self, data: TokenCache) -> None:
        expires_in_value = data.get("expires_in", 3600)
        expiry_seconds = int(expires_in_value)
        payload = dict(data)
        payload["expires_at"] = (datetime.now(UTC) + timedelta(seconds=expiry_seconds)).isoformat()
        TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _admin_request(method: str, path: str, json_body: JSONMapping | None = None) -> JSONValue:
    """Perform an authenticated request to the CJ admin API."""

    manager = AuthManager()
    token = manager.get_token()
    correlation_id = str(uuid.uuid4())
    url = f"{CJ_ADMIN_BASE_URL}{path}"

    with httpx.Client(timeout=30.0) as client:
        resp = client.request(
            method,
            url,
            json=json_body,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Correlation-ID": correlation_id,
                "Content-Type": "application/json",
            },
        )

    if resp.status_code >= 400:
        typer.secho(
            f"Request failed ({resp.status_code}) {resp.text}", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=1)

    if resp.text:
        try:
            parsed = resp.json()
        except ValueError:
            return resp.text
        if isinstance(parsed, (dict, list, str, int, float, bool)) or parsed is None:
            return cast(JSONValue, parsed)
        raise RuntimeError("Unexpected response payload")
    return None


@app.command()
def login(
    email: str = typer.Option(..., prompt=True, help="Identity account email"),
    password: str = typer.Option(
        ..., prompt=True, confirmation_prompt=False, hide_input=True, help="Identity password"
    ),
) -> None:
    """Obtain and cache an admin JWT via the Identity service."""

    manager = AuthManager()
    data = manager.login(email=email, password=password)
    typer.secho("Login successful.", fg=typer.colors.GREEN)
    typer.echo(json.dumps({k: v for k, v in data.items() if k != "refresh_token"}, indent=2))


@token_app.command("issue")
def issue_token(
    email: str | None = typer.Option(
        None,
        help="Identity admin email",
        envvar="CJ_ADMIN_EMAIL",
    ),
    password: str | None = typer.Option(
        None,
        help="Identity admin password",
        envvar="CJ_ADMIN_PASSWORD",
        hide_input=True,
    ),
    cache: bool = typer.Option(
        True,
        help="Cache issued token to ~/.huleedu/cj_admin_token.json",
        show_default=True,
    ),
) -> None:
    """Issue an admin JWT non-interactively using provided credentials."""

    resolved_email = email or CJ_ADMIN_EMAIL
    resolved_password = password or CJ_ADMIN_PASSWORD

    if not resolved_email or not resolved_password:
        typer.secho(
            "Email and password are required. Provide via --email/--password or "
            "CJ_ADMIN_EMAIL/CJ_ADMIN_PASSWORD env vars.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    manager = AuthManager()
    payload = manager.login(email=resolved_email, password=resolved_password)

    if not cache:
        # Remove cached file if it exists to avoid stale credentials when cache disabled
        if TOKEN_CACHE_PATH.exists():
            TOKEN_CACHE_PATH.unlink()

    typer.echo(json.dumps({k: v for k, v in payload.items() if k != "refresh_token"}, indent=2))


def _upload_prompt_helper(assignment_id: str, content: str) -> str:
    """Upload student prompt and return storage_id."""

    payload: dict[str, JSONValue] = {
        "assignment_id": assignment_id,
        "prompt_text": content,
    }
    data = _admin_request("POST", "/student-prompts", json_body=payload)

    if isinstance(data, dict):
        storage_id = data.get("student_prompt_storage_id")
        if isinstance(storage_id, str):
            return storage_id
        raise RuntimeError("student_prompt_storage_id not found in response")
    raise RuntimeError("Unexpected response format from prompt upload")


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

        student_prompt_storage_id = _upload_prompt_helper(assignment_id, prompt_content)
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

    data = _admin_request("POST", "/assessment-instructions", json_body=payload)
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
    data = _admin_request("GET", f"/assessment-instructions{query}")
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

    _admin_request("DELETE", path)
    typer.secho("Instruction deleted", fg=typer.colors.GREEN)


@instructions_app.command("get")
def get_instruction(
    assignment_id: str = typer.Argument(..., help="Assignment ID to fetch"),
) -> None:
    """Retrieve instructions for a specific assignment."""

    data = _admin_request(
        "GET",
        f"/assessment-instructions/assignment/{assignment_id}",
    )
    typer.echo(json.dumps(data, indent=2))


@scales_app.command("list")
def list_scales() -> None:
    """Print registered grade scales."""

    for scale_id, metadata in GRADE_SCALES.items():
        typer.echo(f"{scale_id}: {metadata.display_name} ({len(metadata.grades)} grades)")


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

    # Upload prompt via API
    payload: dict[str, JSONValue] = {
        "assignment_id": assignment_id,
        "prompt_text": content,
    }
    data = _admin_request("POST", "/student-prompts", json_body=payload)

    # Extract and display key information
    if isinstance(data, dict):
        storage_id = data.get("student_prompt_storage_id", "unknown")
        typer.secho("Student prompt uploaded successfully", fg=typer.colors.GREEN)
        typer.echo(f"Assignment ID: {assignment_id}")
        typer.echo(f"Storage ID: {storage_id}")
        typer.echo("")
        typer.echo(json.dumps(data, indent=2))
    else:
        typer.secho("Upload succeeded but response format unexpected", fg=typer.colors.YELLOW)
        typer.echo(json.dumps(data, indent=2))


@prompts_app.command("get")
def get_prompt(
    assignment_id: str = typer.Argument(..., help="Assignment ID to fetch prompt for"),
    output_file: Path | None = typer.Option(None, help="Optional file path to write prompt to"),
) -> None:
    """Fetch student prompt for an assignment."""

    # Fetch prompt via API
    data = _admin_request("GET", f"/student-prompts/assignment/{assignment_id}")

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


if __name__ == "__main__":
    app()
