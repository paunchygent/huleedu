from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from services.api_gateway_service.config import settings


def get_user_id_key(request: Request) -> str:
    # This function assumes that the user_id is stored in the request state
    # by the authentication dependency.
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return str(user_id)
    # Fallback to IP address if user is not authenticated
    return get_remote_address(request)


use_distributed = settings.is_production() or os.getenv("ENV_TYPE") == "docker"

limiter: Limiter
if use_distributed and settings.REDIS_URL:
    # Use Redis via storage_uri for typed compatibility
    limiter = Limiter(
        key_func=get_user_id_key,
        default_limits=[f"{settings.RATE_LIMIT_REQUESTS}/minute"],
        storage_uri=settings.REDIS_URL,
    )
else:
    # In dev/test outside Docker or without Redis URL, use in-memory storage
    limiter = Limiter(
        key_func=get_user_id_key,
        default_limits=[f"{settings.RATE_LIMIT_REQUESTS}/minute"],
    )
