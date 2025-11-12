"""Shared JWT validation helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import jwt
from jwt import exceptions as jwt_exceptions

from huleedu_service_libs.error_handling import raise_authentication_error
from huleedu_service_libs.logging_utils import create_service_logger

from .jwt_settings import JWTValidationSettings

logger = create_service_logger("huleedu_service_libs.auth.jwt")


def decode_and_validate_jwt(
    token: str,
    settings: JWTValidationSettings,
    *,
    correlation_id: UUID,
    service: str,
    operation: str = "validate_jwt",
) -> dict[str, Any]:
    """Decode and validate a JWT using shared settings.

    Args:
        token: Raw Bearer token string.
        settings: Service settings that include :class:`JWTValidationSettings`.
        correlation_id: Correlation identifier for structured errors.
        service: Service name for error reporting.
        operation: Logical operation name for error reporting.

    Returns:
        The decoded payload dict.

    Raises:
        HuleEduError: Wrapped authentication failures via Rule 048 factories.
    """

    try:
        key = settings.get_jwt_verification_key()
    except Exception as exc:  # noqa: BLE001
        raise_authentication_error(
            service=service,
            operation=operation,
            message="JWT verification key not configured",
            correlation_id=correlation_id,
            reason="jwt_key_missing",
            error=str(exc),
        )

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )
    except jwt_exceptions.ExpiredSignatureError:
        raise_authentication_error(
            service=service,
            operation=operation,
            message="Token has expired",
            correlation_id=correlation_id,
            reason="token_expired",
        )
    except jwt_exceptions.InvalidAudienceError as exc:
        raise_authentication_error(
            service=service,
            operation=operation,
            message="Invalid token audience",
            correlation_id=correlation_id,
            reason="invalid_audience",
            expected_audience=settings.JWT_AUDIENCE,
            error=str(exc),
        )
    except jwt_exceptions.InvalidIssuerError as exc:
        raise_authentication_error(
            service=service,
            operation=operation,
            message="Invalid token issuer",
            correlation_id=correlation_id,
            reason="invalid_issuer",
            expected_issuer=settings.JWT_ISSUER,
            error=str(exc),
        )
    except jwt_exceptions.InvalidSignatureError as exc:
        raise_authentication_error(
            service=service,
            operation=operation,
            message="Invalid token signature",
            correlation_id=correlation_id,
            reason="invalid_signature",
            error=str(exc),
        )
    except jwt_exceptions.InvalidAlgorithmError as exc:
        raise_authentication_error(
            service=service,
            operation=operation,
            message="Algorithm not allowed",
            correlation_id=correlation_id,
            reason="invalid_algorithm",
            error=str(exc),
        )
    except jwt_exceptions.InvalidSubjectError as exc:
        raise_authentication_error(
            service=service,
            operation=operation,
            message="Subject must be a string",
            correlation_id=correlation_id,
            reason="invalid_subject",
            error=str(exc),
        )
    except jwt_exceptions.InvalidTokenError as exc:
        raise_authentication_error(
            service=service,
            operation=operation,
            message="Invalid token",
            correlation_id=correlation_id,
            reason="invalid_token",
            error=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        raise_authentication_error(
            service=service,
            operation=operation,
            message="Failed to validate token",
            correlation_id=correlation_id,
            reason="jwt_validation_failure",
            error=str(exc),
        )

    exp_timestamp = payload.get("exp")
    if exp_timestamp is None:
        raise_authentication_error(
            service=service,
            operation=operation,
            message="Token missing expiration claim",
            correlation_id=correlation_id,
            reason="missing_exp",
        )

    current_time = datetime.now(UTC).timestamp()
    if current_time >= float(exp_timestamp):
        raise_authentication_error(
            service=service,
            operation=operation,
            message="Token has expired",
            correlation_id=correlation_id,
            reason="token_expired",
        )

    return payload


def try_decode_and_validate_jwt(
    token: str,
    settings: JWTValidationSettings,
    *,
    correlation_id: UUID,
    service: str,
    operation: str = "validate_jwt",
) -> dict[str, Any] | None:
    """Best-effort decoding wrapper that swallows failures."""

    try:
        return decode_and_validate_jwt(
            token,
            settings,
            correlation_id=correlation_id,
            service=service,
            operation=operation,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("JWT bridge decode failed: %s", exc)
        return None
