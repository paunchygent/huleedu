"""Utilities for the CLI."""

from __future__ import annotations

import uuid
from typing import Mapping, TypeAlias, cast

import httpx
import typer

from services.cj_assessment_service.cli.auth import AuthManager
from services.cj_assessment_service.cli.config import CJ_ADMIN_BASE_URL

JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | dict[str, "JSONValue"] | list["JSONValue"]
JSONMapping: TypeAlias = Mapping[str, JSONValue]


def make_admin_request(method: str, path: str, json_body: JSONMapping | None = None) -> JSONValue:
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
        # Provide hint for common "not found" errors
        resp_lower = resp.text.lower()
        if "not found" in resp_lower or resp.status_code == 404:
            typer.secho(
                "Hint: Run `cj-admin instructions list` to see existing assignment IDs",
                fg=typer.colors.YELLOW,
                err=True,
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
