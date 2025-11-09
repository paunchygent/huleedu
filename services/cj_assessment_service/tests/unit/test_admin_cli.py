"""Tests for CJ admin CLI utilities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch

from services.cj_assessment_service import cli_admin


def test_auth_manager_uses_override(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(cli_admin, "CJ_ADMIN_TOKEN_OVERRIDE", "override-token")
    manager = cli_admin.AuthManager()
    assert manager.get_token() == "override-token"


def test_auth_manager_cache_round_trip(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    cache_path = tmp_path / "token.json"
    monkeypatch.setattr(cli_admin, "CJ_ADMIN_TOKEN_OVERRIDE", None)
    monkeypatch.setattr(cli_admin, "TOKEN_CACHE_PATH", cache_path)

    manager = cli_admin.AuthManager()
    payload: cli_admin.TokenCache = {
        "access_token": "cached-token",
        "refresh_token": "refresh-token",
        "expires_in": 3600,
    }
    manager._save_cache(payload)  # pylint: disable=protected-access

    cached = manager._load_cache()  # pylint: disable=protected-access
    assert cached is not None
    assert cached["access_token"] == "cached-token"
    future_payload: cli_admin.TokenCache = {
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    }
    assert manager._is_expired(future_payload) is False
    expired_payload: cli_admin.TokenCache = {"expires_at": datetime.now(UTC).isoformat()}
    assert manager._is_expired(expired_payload) is True
