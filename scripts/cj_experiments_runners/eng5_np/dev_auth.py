"""Development-only JWT generation for CLI scripts.

⚠️  DEVELOPMENT ONLY - FORBIDDEN IN PRODUCTION ⚠️

Generates admin JWT tokens using CJ Assessment Service settings.
Multiple safety gates prevent production use.

USAGE (AI/Scripts):
    from scripts.cj_experiments_runners.eng5_np.cj_client import build_admin_headers
    headers = build_admin_headers()  # Auto-generates token in dev

Production: Set HULEEDU_SERVICE_ACCOUNT_TOKEN env var.
"""

from __future__ import annotations

import os
from datetime import timedelta

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.testing.jwt_helpers import build_jwt_headers

from services.cj_assessment_service.config import Settings

logger = create_service_logger("eng5_np.dev_auth")

# Gate 1: Import-time environment check
_ENV = os.getenv("ENVIRONMENT", "development").upper()
_H_ENV = os.getenv("HULEEDU_ENVIRONMENT", "development").upper()

if _ENV in ("PRODUCTION", "STAGING", "PROD") or _H_ENV in (
    "PRODUCTION",
    "STAGING",
    "PROD",
):
    raise RuntimeError(
        f"dev_auth.py cannot be imported in production. "
        f"ENVIRONMENT={_ENV}, HULEEDU_ENVIRONMENT={_H_ENV}. "
        "Use service accounts instead."
    )


def _ensure_dev_environment() -> None:
    """Gate 2: Runtime environment validation."""
    env = os.getenv("ENVIRONMENT", "development").upper()
    h_env = os.getenv("HULEEDU_ENVIRONMENT", "development").upper()

    if env in ("PRODUCTION", "STAGING", "PROD") or h_env in (
        "PRODUCTION",
        "STAGING",
        "PROD",
    ):
        raise RuntimeError("Development JWT generation forbidden in production.")


def create_dev_admin_token(
    subject: str = "cj-admin-dev-cli",
    org_id: str | None = None,
    expires_in: timedelta = timedelta(hours=1),
) -> str:
    """
    Create development admin JWT for CJ admin endpoints.

    Uses CJ Assessment Service JWT settings (issuer, audience, secret).
    Grants roles=["admin"] for admin endpoint access.

    Args:
        subject: JWT subject claim (user identifier)
        org_id: Optional organization ID
        expires_in: Token validity duration

    Returns:
        Encoded JWT token string

    Raises:
        RuntimeError: If called in production environment
    """
    _ensure_dev_environment()

    # Audit trail: Log every token generation for security monitoring
    logger.warning(
        "using_development_jwt_generation",
        subject=subject,
        org_id=org_id,
        expires_in_seconds=int(expires_in.total_seconds()),
        security_warning="NOT_FOR_PRODUCTION_USE",
    )

    # Use CJ service settings (same as require_admin validates against)
    # JWT_SECRET_KEY now has validation_alias, so it reads from global env var
    settings = Settings()

    # Reuse test helper (produces compatible token)
    headers = build_jwt_headers(
        settings,
        subject=subject,
        roles=["admin"],
        org_id=org_id,
        expires_in=expires_in,
    )

    # Extract token from Authorization header
    auth_header = headers["Authorization"]
    _, token = auth_header.split(" ", 1)
    return token
