"""Typer-based admin helper for CJ assessment service."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, TypeAlias, TypedDict, cast

import httpx
import typer
from common_core.grade_scales import GRADE_SCALES

IDENTITY_BASE_URL = os.getenv("IDENTITY_BASE_URL", "http://localhost:7005/v1/auth")
CJ_ADMIN_BASE_URL = os.getenv("CJ_ADMIN_BASE_URL", "http://localhost:9095/admin/v1")
TOKEN_CACHE_PATH = Path(
    os.getenv("CJ_ADMIN_TOKEN_PATH", Path.home() / ".huleedu" / "cj_admin_token.json")
)
CJ_ADMIN_TOKEN_OVERRIDE = os.getenv("CJ_ADMIN_TOKEN")

app = typer.Typer(help="CJ Assessment admin CLI")
instructions_app = typer.Typer(help="Manage assessment instructions")
app.add_typer(instructions_app, name="instructions")
scales_app = typer.Typer(help="Inspect registered grade scales")
app.add_typer(scales_app, name="scales")

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


@instructions_app.command("create")
def create_instruction(
    assignment_id: str = typer.Option("", help="Assignment ID (mutually exclusive with course)"),
    course_id: str = typer.Option("", help="Course ID when assignment ID is not provided"),
    instructions_file: Path | None = typer.Option(
        None, help="Path to a markdown/text file containing the instructions"
    ),
    instructions_text: str = typer.Option("", help="Inline instructions text when no file is given"),
    grade_scale: str = typer.Option(..., help="Registered grade scale ID"),
) -> None:
    """Create or update assessment instructions."""

    if bool(assignment_id) == bool(course_id):
        typer.secho("Provide exactly one of --assignment-id or --course-id", fg=typer.colors.RED)
        raise typer.Exit(code=2)

    if instructions_file:
        instructions = instructions_file.read_text(encoding="utf-8")
    elif instructions_text:
        instructions = instructions_text
    else:
        instructions = typer.prompt("Instructions text")

    payload: dict[str, JSONValue] = {
        "assignment_id": assignment_id or None,
        "course_id": course_id or None,
        "instructions_text": instructions,
        "grade_scale": grade_scale,
    }
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
def get_instruction(assignment_id: str = typer.Argument(..., help="Assignment ID to fetch")) -> None:
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


if __name__ == "__main__":
    app()
