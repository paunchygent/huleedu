"""Helpers for queue TTL evaluation and labeling."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.llm_provider_service.queue_models import QueuedRequest


def is_request_expired(request: QueuedRequest, *, now: datetime | None = None) -> bool:
    """Check if a queued request has expired."""

    current_time = now or datetime.now(timezone.utc)
    expiry_time = request.queued_at + request.ttl
    return current_time > expiry_time


def normalize_ttl_label(ttl: Any) -> str:
    """Normalize TTL labels to Prometheus-friendly values."""

    if ttl is None:
        return "none"
    ttl_str = str(ttl).lower().strip()
    if ttl_str in {"1h", "60m", "3600", "3600s"}:
        return "1h"
    if ttl_str in {"5m", "300", "300s"}:
        return "5m"
    return "none"
