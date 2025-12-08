"""Authentication logic for the CLI."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import TypedDict, cast

import httpx
import jwt
import typer

from services.cj_assessment_service.cli.config import (
    CJ_ADMIN_TOKEN_OVERRIDE,
    HULEEDU_ENVIRONMENT,
    IDENTITY_BASE_URL,
    JWT_SECRET_KEY,
    TOKEN_CACHE_PATH,
)


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

        # Auto-generate dev token in development environment
        if HULEEDU_ENVIRONMENT == "development" and JWT_SECRET_KEY:
            typer.secho("Auto-generating dev admin token...", fg=typer.colors.YELLOW)
            return jwt.encode(
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
