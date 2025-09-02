from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import jwt

from huleedu_service_libs.error_handling import raise_authentication_error
from huleedu_service_libs.logging_utils import create_service_logger
from services.api_gateway_service.config import Settings

logger = create_service_logger("api_gateway.jwt_utils")


def decode_and_validate_jwt(token: str, settings: Settings, correlation_id: UUID) -> dict[str, Any]:
    """
    Decode and validate a JWT using configured settings.

    - Verifies signature, algorithm, and audience
    - Enforces presence of `exp` and validates expiry against current time

    Raises HuleEduError via raise_authentication_error on validation failures.
    Returns the decoded payload dict on success.
    """
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
        audience=settings.JWT_AUDIENCE,
        issuer=settings.JWT_ISSUER,
    )

    exp_timestamp = payload.get("exp")
    if exp_timestamp is None:
        raise_authentication_error(
            service="api_gateway_service",
            operation="validate_jwt",
            message="Token missing expiration claim",
            correlation_id=correlation_id,
            reason="missing_exp",
        )

    current_time = datetime.now(UTC).timestamp()
    if current_time >= exp_timestamp:
        raise_authentication_error(
            service="api_gateway_service",
            operation="validate_jwt",
            message="Token has expired",
            correlation_id=correlation_id,
            reason="token_expired",
        )

    return payload


def try_decode_and_validate_jwt(
    token: str, settings: Settings, correlation_id: UUID
) -> dict[str, Any] | None:
    """
    Best-effort decode for middleware bridging.

    Returns payload dict on success, or None on any failure. Never raises.
    """
    try:
        return decode_and_validate_jwt(token, settings, correlation_id)
    except Exception as e:  # noqa: BLE001
        # Log at debug to avoid noise; auth layer will enforce strictly later
        logger.debug(f"JWT bridge decode failed: {e!s}")
        return None
