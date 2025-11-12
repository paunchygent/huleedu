"""Tests for JWTValidationSettings helper behaviour."""

from __future__ import annotations

import pytest
from huleedu_service_libs.auth.jwt_settings import JWTValidationSettings
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class HSSettings(BaseSettings, JWTValidationSettings):
    """Test settings that exercise HS* algorithm configuration."""

    model_config = SettingsConfigDict(arbitrary_types_allowed=True)


class RSSettings(BaseSettings, JWTValidationSettings):
    """Test settings that exercise RS* algorithm configuration."""

    model_config = SettingsConfigDict(arbitrary_types_allowed=True)


class TestJWTValidationSettings:
    """Validate shared JWT configuration helpers."""

    def test_hs_algorithm_requires_secret_key(self) -> None:
        settings = HSSettings(
            JWT_ALGORITHM="HS256", JWT_AUDIENCE="test-audience", JWT_ISSUER="test-issuer"
        )

        with pytest.raises(ValueError, match="JWT_SECRET_KEY must be configured"):
            settings.get_jwt_verification_key()

    def test_hs_algorithm_with_secret_key(self) -> None:
        settings = HSSettings(
            JWT_ALGORITHM="HS256",
            JWT_AUDIENCE="test-audience",
            JWT_ISSUER="test-issuer",
            JWT_SECRET_KEY=SecretStr("super-secret"),
        )

        key = settings.get_jwt_verification_key()
        assert key == "super-secret"

    def test_rs_algorithm_allows_public_key_without_secret(self) -> None:
        settings = RSSettings(
            JWT_ALGORITHM="RS256",
            JWT_AUDIENCE="test-audience",
            JWT_ISSUER="test-issuer",
            JWT_PUBLIC_KEY="public-key",
        )

        key = settings.get_jwt_verification_key()
        assert key == "public-key"
