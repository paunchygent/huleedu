"""Main entrypoint for the CLI."""

from __future__ import annotations

import json

import typer

from services.cj_assessment_service.cli.auth import AuthManager
from services.cj_assessment_service.cli.instructions import instructions_app
from services.cj_assessment_service.cli.prompts import prompts_app
from services.cj_assessment_service.cli.rubrics import rubrics_app
from services.cj_assessment_service.cli.scales import scales_app
from services.cj_assessment_service.cli.token import token_app

app = typer.Typer(help="CJ Assessment admin CLI")

app.add_typer(instructions_app, name="instructions")
app.add_typer(scales_app, name="scales")
app.add_typer(prompts_app, name="prompts")
app.add_typer(rubrics_app, name="rubrics")
app.add_typer(token_app, name="token")


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
