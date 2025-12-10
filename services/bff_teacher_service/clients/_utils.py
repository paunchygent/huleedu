"""Shared utilities for BFF Teacher Service HTTP clients."""

from __future__ import annotations

from uuid import UUID

from services.bff_teacher_service.config import settings


def build_internal_auth_headers(correlation_id: UUID) -> dict[str, str]:
    """Build authentication headers for internal service calls.

    Args:
        correlation_id: Request correlation ID for distributed tracing

    Returns:
        Headers dict with internal API key, service ID, and correlation ID
    """
    return {
        "X-Internal-API-Key": settings.get_internal_api_key(),
        "X-Service-ID": settings.SERVICE_NAME,
        "X-Correlation-ID": str(correlation_id),
    }
