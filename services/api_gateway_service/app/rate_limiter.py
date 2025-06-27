from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from ..config import settings


def get_user_id_key(request: Request) -> str:
    # This function assumes that the user_id is stored in the request state
    # by the authentication dependency.
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return str(user_id)
    # Fallback to IP address if user is not authenticated
    return get_remote_address(request)


limiter = Limiter(
    key_func=get_user_id_key, default_limits=[f"{settings.RATE_LIMIT_REQUESTS}/minute"]
)
