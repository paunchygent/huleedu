"""Shared JWT validation settings mixin."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from pydantic import Field, SecretStr


class JWTValidationSettings:
    """Mixin that adds JWT validation configuration to service settings."""

    JWT_ALGORITHM: str = Field(
        default="HS256",
        description="JWT signing/validation algorithm (e.g., HS256, RS256)",
    )
    JWT_AUDIENCE: str = Field(
        default="huleedu-platform",
        description="Expected JWT audience claim",
    )
    JWT_ISSUER: str = Field(
        default="huleedu-identity-service",
        description="Expected JWT issuer claim",
    )
    JWT_SECRET_KEY: SecretStr | None = Field(
        default=None,
        description="Shared secret for verifying HS* tokens",
    )
    JWT_PUBLIC_KEY: str | None = Field(
        default=None,
        description="PEM-encoded public key for RS*/ES* tokens",
    )
    JWT_PUBLIC_KEY_PATH: str | None = Field(
        default=None,
        description="Path to PEM public key file for RS*/ES* tokens",
    )
    JWT_JWKS_URL: str | None = Field(
        default=None,
        description="Optional JWKS endpoint for remote key discovery (not yet used)",
    )

    _HS_PREFIXES: Final[tuple[str, ...]] = ("HS",)

    def get_jwt_verification_key(self) -> str:
        """Resolve the key used to verify JWT signatures."""

        if self._uses_hmac() and self.JWT_SECRET_KEY is not None:
            return self.JWT_SECRET_KEY.get_secret_value()

        if self.JWT_PUBLIC_KEY:
            return self.JWT_PUBLIC_KEY

        if self.JWT_PUBLIC_KEY_PATH:
            path = Path(self.JWT_PUBLIC_KEY_PATH).expanduser().resolve()
            return path.read_text(encoding="utf-8")

        raise ValueError(
            "No JWT verification key configured. Set JWT_SECRET_KEY, "
            "JWT_PUBLIC_KEY, or JWT_PUBLIC_KEY_PATH."
        )

    def _uses_hmac(self) -> bool:
        """Return True if the configured algorithm uses an HS* secret."""

        algorithm = self.JWT_ALGORITHM.upper()
        return any(algorithm.startswith(prefix) for prefix in self._HS_PREFIXES)
