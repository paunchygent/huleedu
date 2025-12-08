"""Token management commands."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import jwt
import typer

from services.cj_assessment_service.cli.auth import AuthManager, TokenCache
from services.cj_assessment_service.cli.config import (
    CJ_ADMIN_EMAIL,
    CJ_ADMIN_PASSWORD,
    HULEEDU_ENVIRONMENT,
    JWT_SECRET_KEY,
    TOKEN_CACHE_PATH,
)

token_app = typer.Typer(help="Admin token utilities")


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


@token_app.command("dev")
def dev_token(
    cache: bool = typer.Option(
        False,
        help="Cache the generated token to ~/.huleedu/cj_admin_token.json",
    ),
) -> None:
    """Generate a dev admin token using JWT_SECRET_KEY (development only)."""
    if HULEEDU_ENVIRONMENT != "development":
        typer.secho(
            "Dev tokens only available in development environment", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=1)

    if not JWT_SECRET_KEY:
        typer.secho("JWT_SECRET_KEY not set in environment", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    token = jwt.encode(
        {
            "sub": "dev-admin",
            "email": "dev-admin@huleedu.local",
            "roles": ["admin"],
            "aud": "huleedu-platform",
            "iss": "huleedu-identity-service",
            "exp": datetime.now(UTC) + timedelta(hours=24),
        },
        JWT_SECRET_KEY,
        algorithm="HS256",
    )

    if cache:
        cache_data: TokenCache = {
            "access_token": token,
            "expires_in": 86400,
        }
        TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_CACHE_PATH.write_text(json.dumps(cache_data, indent=2), encoding="utf-8")
        typer.secho(f"Token cached to {TOKEN_CACHE_PATH}", fg=typer.colors.GREEN)

    typer.echo(token)
