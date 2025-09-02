from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

import os
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
if use_distributed:
    try:
        # Prefer explicit storage when available (newer SlowAPI versions)
        from slowapi.storage import RedisStorage  # type: ignore

        storage = RedisStorage(settings.REDIS_URL) if settings.REDIS_URL else None
        limiter = Limiter(
            key_func=get_user_id_key,
            default_limits=[f"{settings.RATE_LIMIT_REQUESTS}/minute"],
            storage=storage,
        )
    except Exception:
        # Fallback for SlowAPI versions without RedisStorage
        limiter = Limiter(
            key_func=get_user_id_key,
            default_limits=[f"{settings.RATE_LIMIT_REQUESTS}/minute"],
            storage_uri=settings.REDIS_URL,
        )
else:
    # In dev/test outside Docker, use in-memory storage to avoid Redis dependency
    limiter = Limiter(
        key_func=get_user_id_key,
        default_limits=[f"{settings.RATE_LIMIT_REQUESTS}/minute"],
    )
