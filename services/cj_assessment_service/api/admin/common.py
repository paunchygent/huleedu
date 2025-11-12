"""Shared helpers for CJ admin blueprints."""

from __future__ import annotations

from typing import Any

from huleedu_service_libs.auth import decode_and_validate_jwt
from huleedu_service_libs.error_handling import (
    raise_authentication_error,
    raise_authorization_error,
)
from huleedu_service_libs.error_handling.correlation import (
    CorrelationContext,
    extract_correlation_context_from_request,
)
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, current_app, g, request

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.metrics import get_metrics

logger = create_service_logger("cj_assessment_service.api.admin")

_ADMIN_METRIC_KEY = "admin_instruction_operations"


async def require_admin() -> None:
    """Authenticate admin access using Identity Service JWTs."""

    settings: Settings = current_app.config["settings"]
    correlation: CorrelationContext = extract_correlation_context_from_request(request)
    authorization = request.headers.get("Authorization")

    if not authorization:
        raise_authentication_error(
            service="cj_assessment_service",
            operation="admin_auth",
            message="Authorization header required",
            correlation_id=correlation.uuid,
            reason="missing_authorization_header",
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise_authentication_error(
            service="cj_assessment_service",
            operation="admin_auth",
            message="Expected 'Authorization: Bearer <token>'",
            correlation_id=correlation.uuid,
            reason="invalid_authorization_format",
        )

    token = parts[1]
    payload: dict[str, Any] = decode_and_validate_jwt(
        token,
        settings,
        correlation_id=correlation.uuid,
        service="cj_assessment_service",
        operation="admin_auth",
    )

    roles = payload.get("roles")
    if not isinstance(roles, list) or "admin" not in roles:
        raise_authorization_error(
            service="cj_assessment_service",
            operation="admin_auth",
            message="Admin role required",
            correlation_id=correlation.uuid,
            required_role="admin",
        )

    g.admin_payload = payload
    g.correlation_context = correlation


def register_admin_auth(bp: Blueprint) -> None:
    """Attach admin authentication requirement to blueprint."""

    bp.before_request(require_admin)  # type: ignore[arg-type]


def record_admin_metric(operation: str, status: str) -> None:
    """Increment shared Prometheus counter for admin operations."""

    metrics = get_metrics()
    counter = metrics.get(_ADMIN_METRIC_KEY)
    if counter is not None:
        counter.labels(operation=operation, status=status).inc()


__all__ = ["record_admin_metric", "register_admin_auth", "require_admin"]
