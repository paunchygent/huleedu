"""
Shared JWT test helpers for creating test authentication tokens.

Provides flexible, settings-aware functions for creating JWT tokens in tests
with support for edge cases like expired tokens, missing claims, and custom
payloads. Replaces scattered local helpers across service tests.

Usage Examples:
    # Standard user token:
    headers = build_jwt_headers(settings, subject="user-123")

    # Admin token with roles:
    headers = build_jwt_headers(settings, subject="admin", roles=["admin"])

    # Expired token for expiry testing:
    headers = build_jwt_headers(settings, expires_in=timedelta(hours=-1))

    # Token missing exp claim:
    headers = build_jwt_headers(settings, omit_claims=["exp"])

    # Token with custom org claim:
    headers = build_jwt_headers(settings, extra_claims={"organization_id": "org-123"})
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Sequence
from uuid import uuid4

import jwt
from huleedu_service_libs.auth.jwt_settings import JWTValidationSettings
from pydantic import SecretStr


def build_jwt_headers(
    settings: JWTValidationSettings,
    *,
    subject: str = "test-user",
    roles: Sequence[str] | None = None,
    org_id: str | None = None,
    correlation_id: str | None = None,
    expires_in: timedelta = timedelta(hours=1),
    omit_claims: Sequence[str] | None = None,
    extra_claims: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """
    Build complete HTTP headers with JWT Authorization for testing.

    Creates a signed JWT token and returns headers dict with:
    - Authorization: Bearer <token>
    - X-Correlation-ID: <correlation_id or auto-generated>

    Args:
        settings: Service settings with JWT configuration
        subject: JWT subject claim (user_id), defaults to "test-user"
        roles: List of roles to include in token
        org_id: Organization ID to include as "org_id" claim
        correlation_id: Optional correlation ID for request tracking
        expires_in: Token validity duration (can be negative for expired tokens)
        omit_claims: Claims to exclude from payload (e.g., ["exp", "sub"])
        extra_claims: Additional custom claims to include

    Returns:
        Dict with Authorization and X-Correlation-ID headers

    Examples:
        >>> # Standard user token
        >>> headers = build_jwt_headers(settings, subject="user-123")

        >>> # Admin token with roles
        >>> headers = build_jwt_headers(settings, subject="admin", roles=["admin"])

        >>> # Expired token (for expiry testing)
        >>> headers = build_jwt_headers(settings, expires_in=timedelta(hours=-1))

        >>> # Missing exp claim (for validation testing)
        >>> headers = build_jwt_headers(settings, omit_claims=["exp"])
    """
    # Build base payload
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_in).timestamp()),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }

    # Add optional claims
    if roles:
        payload["roles"] = list(roles)

    if org_id:
        payload["org_id"] = org_id

    # Merge extra claims
    if extra_claims:
        payload.update(extra_claims)

    # Remove specified claims (for negative testing)
    omit_set = set(omit_claims or [])
    for claim in omit_set:
        payload.pop(claim, None)

    # Create token
    token = create_jwt(
        secret=_get_secret_from_settings(settings),
        payload=payload,
        algorithm=settings.JWT_ALGORITHM,
    )

    # Build headers
    return {
        "Authorization": f"Bearer {token}",
        "X-Correlation-ID": correlation_id or str(uuid4()),
    }


def create_jwt(
    secret: str,
    payload: dict[str, Any],
    algorithm: str = "HS256",
) -> str:
    """
    Create a JWT token from a custom payload.

    Low-level helper for full control over token creation. Most tests should
    use build_jwt_headers() instead for settings integration.

    Args:
        secret: Signing secret key
        payload: Complete JWT payload dict
        algorithm: JWT signing algorithm (default: HS256)

    Returns:
        Encoded JWT token string

    Examples:
        >>> # Custom payload for edge case testing
        >>> payload = {"sub": "test", "custom": "value"}
        >>> token = create_jwt("secret", payload)
    """
    return jwt.encode(payload, secret, algorithm=algorithm)


def _get_secret_from_settings(settings: JWTValidationSettings) -> str:
    """
    Extract JWT secret from settings object.

    Handles both SecretStr and plain string values.

    Args:
        settings: Settings object with JWT_SECRET_KEY

    Returns:
        Secret key as plain string

    Raises:
        RuntimeError: If JWT_SECRET_KEY is not configured
    """
    secret = settings.JWT_SECRET_KEY

    if secret is None:
        raise RuntimeError(
            "JWT_SECRET_KEY must be configured for JWT test helpers. "
            "Ensure your test settings include a JWT_SECRET_KEY value."
        )

    # Handle SecretStr type
    if isinstance(secret, SecretStr):
        return secret.get_secret_value()

    # Handle plain string (should not happen with typed settings, but be defensive)
    return str(secret)


__all__ = [
    "build_jwt_headers",
    "create_jwt",
]
